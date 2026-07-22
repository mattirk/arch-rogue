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
import os
import random
import time
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
    DEFAULT_FRAME_RATE,
    DUNGEON_DEPTH,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    FPS,
    FRAME_RATE_CAP_DEFAULT,
    FRAME_RATE_CAP_VALUES,
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
    normalize_frame_rate_cap,
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
from .input import Command, InputMixin, key_command
from .interactions import InteractionMixin
from .inventory import InventoryMixin
from .menus import MenuRenderer
from .mobile import (
    MobileMixin,
    SafeInsets,
    application_storage_directory,
    detect_mobile_runtime,
)
from .net import NetMixin
from .text_input import TextInputMixin
from .story import FriendlyNpcRuntimeMixin
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
from .options import (
    DEFAULT_MP_SERVER_HOST,
    DEFAULT_MP_SERVER_PORT,
    OptionsMixin,
    default_mobile_render_quality,
)
from .population import PopulationMixin
from .story import (
    ActiveQuestCutscene,
    RuntimeDialogueChoice,
    format_asset_text,
    load_quest_cutscene_library,
)
from .rendering import RenderingMixin
from .run_flow import RunFlowMixin
from .save_system import SaveLoadMixin
from .shop import ShopMixin
from .sprites import PixelSpriteAtlas, SpriteAtlas, UiAssetLibrary
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
from .story import StoryRuntimeMixin

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
    "FRAME_RATE_CAP_DEFAULT",
    "FRAME_RATE_CAP_VALUES",
    "FloatingText",
    "FloorPlan",
    "FriendlyNpcRuntimeMixin",
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
    "MobileMixin",
    "OptionsMixin",
    "PLAYER_HIT_RADIUS",
    "PLAYER_MELEE_ARC_DOT",
    "PLAYER_MELEE_RANGE",
    "PLAYER_PROJECTILE_HIT_RADIUS",
    "PixelSpriteAtlas",
    "FramePacing",
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


class FramePacing:
    """Single owner of frame timing for ``Game.run()``.

    Replaces the scattered ``clock.tick(FPS)`` / ``clock.tick(10)`` calls with
    one object that reads the persisted ``frame_rate_cap`` option and the
    mobile suspended-mode throttle. ``Game.run()`` is the only caller of
    :meth:`tick`; the dt clamp (``0.05``) and the
    ``min(clock.tick(target) / 1000.0, 0.05)`` shape are preserved verbatim —
    only the source of ``target_fps`` changes.
    """

    def __init__(self, clock: pygame.time.Clock) -> None:
        self._clock = clock
        # User-facing option (one of FRAME_RATE_CAP_VALUES). Default is 60.
        self.frame_rate_cap: int | str = FRAME_RATE_CAP_DEFAULT
        # Resolved tick target. ``0`` means unlimited (``clock.tick(0)`` returns
        # elapsed ms without waiting). Suspended mode overrides this regardless.
        self.target_fps: int = int(FRAME_RATE_CAP_DEFAULT)
        # Mobile suspended-mode throttle (Hz). Used only when Android is
        # backgrounded; desktop never suspends.
        self.suspended_fps: int = 10
        # vsync hint. SDL's ``SCALED`` renderer handles vsync internally on
        # Android; desktop leaves this off so the cap is the only throttle.
        self.vsync: bool = False

    def set_frame_rate_cap(self, cap: int | str) -> None:
        normalized = normalize_frame_rate_cap(cap)
        self.frame_rate_cap = normalized
        if normalized == "Unlimited":
            self.target_fps = 0
        else:
            self.target_fps = int(normalized)

    def tick(self, *, suspended: bool = False) -> float:
        if suspended:
            fps = self.suspended_fps
        else:
            fps = self.target_fps
        return min(self._clock.tick(fps) / 1000.0, 0.05)


class Game(
    SaveLoadMixin,
    RenderingMixin,
    OptionsMixin,
    RunFlowMixin,
    PopulationMixin,
    StoryRuntimeMixin,
    FriendlyNpcRuntimeMixin,
    CombatMixin,
    InventoryMixin,
    ShopMixin,
    InteractionMixin,
    InputMixin,
    MobileMixin,
    NetMixin,
    TextInputMixin,
    CameraMixin,
):
    EXIT_CONFIRMATION_EXIT = 0
    EXIT_CONFIRMATION_MAIN_MENU = 1
    EXIT_CONFIRMATION_CANCEL = 2
    EXIT_CONFIRMATION_OPTION_COUNT = 3

    def __init__(
        self,
        screen_size: tuple[int, int] | None = None,
        headless: bool = False,
        save_path: str | Path | None = None,
        mobile: bool | None = None,
        safe_insets: SafeInsets | tuple[int, int, int, int] | None = None,
        eager_tile_prewarm: bool | None = None,
    ) -> None:
        self.mobile_mode = detect_mobile_runtime() if mobile is None else bool(mobile)
        # Interactive builds pre-generate every themed tile variant to avoid a
        # transition hitch. Headless tests build only the variants they render,
        # unless a cache-contract test explicitly requests eager warming.
        self.eager_tile_prewarm = (
            not headless
            if eager_tile_prewarm is None
            else bool(eager_tile_prewarm)
        )
        if self.mobile_mode:
            # SDL otherwise exposes the Android accelerometer as a joystick. Set
            # the hint before subsystem initialization; ControllerManager also
            # filters named sensors defensively for SDL/vendor variations.
            os.environ["SDL_ACCELEROMETER_AS_JOYSTICK"] = "0"
        self.prepare_display_scaling()
        pygame.init()
        pygame.display.set_caption(f"Arch Rogue {__version__}")
        storage_dir = application_storage_directory(self.mobile_mode)
        self.save_path = (
            Path(save_path)
            if save_path
            else storage_dir
            / ("run.json" if self.mobile_mode else ".arch_rogue_run.json")
        )
        self.options_path = storage_dir / (
            "options.json" if self.mobile_mode else ".arch_rogue_options.json"
        )
        self.audio_enabled = True
        self.music_enabled = False
        self.fullscreen = True
        self.mobile_render_quality = default_mobile_render_quality(self.mobile_mode)
        self.ui_scale = UI_SCALE
        self.ui_scale_auto = True
        self.detected_display_scale: float | None = None
        self.controller_enabled = True
        self.last_controller_guid = ""
        self.difficulty_name = DEFAULT_DIFFICULTY_NAME
        self.hell_unlocked = False
        self.hell_unlocked_this_run = False
        # Milestone 3.16 - continuous colored lighting options. Normal maps stay
        # on by default on desktop, but fresh mobile installs avoid their cold
        # ARM cache spike. The web build forces lighting off in web/main.make_game.
        self._lighting_enabled = True
        self._lighting_normal_maps = not self.mobile_mode
        # 4.3.17 schema-7 options. Defaults keep desktop telemetry silent and a
        # 60 FPS cap on both platforms; load_options() overrides from disk.
        self.frame_rate_cap: int | str = FRAME_RATE_CAP_DEFAULT
        self.show_perf_overlay: bool = False
        # Asset sprites are the production default. The persisted legacy toggle
        # keeps the original procedural renderer available on constrained systems
        # and as a per-install compatibility fallback.
        self.legacy_graphics = False
        self.meta_progress: dict[str, Any] = self.default_meta_progress()
        self.run_history: list[dict[str, Any]] = []
        # 4.6 schema-8 multiplayer options. load_options() overrides from disk;
        # the endpoint starts on the public default server.
        self.mp_player_name = ""
        self.mp_server_host = DEFAULT_MP_SERVER_HOST
        self.mp_server_port = DEFAULT_MP_SERVER_PORT
        self.last_save_error = ""
        self.last_load_error = ""
        self.recovered_interrupted_run = False
        self.screen_flash_ttl = 0.0
        self.screen_flash_color: Color = (0, 0, 0)
        # Viewport zoom ("viewport distance"); adjusted in-game with Ctrl+scroll.
        # Desktop defaults to the widest view (max zoomed out) so players see
        # more of the dungeon at once; mobile keeps native scale since its
        # landscape layout and touch targets are tuned for 1.0.
        self.view_zoom = 1.0 if self.mobile_mode else self.VIEW_ZOOM_MIN
        self._world_layer: pygame.Surface | None = None
        # Headless callers (tests, benchmarks, tooling) must not inherit the
        # developer machine's real home-directory preferences before they can
        # install an isolated options_path. They can still call load_options()
        # explicitly after setting that path, as persistence tests already do.
        if not headless:
            self.load_options()
        if self.mobile_mode:
            # Android is landscape/fullscreen by manifest; a persisted desktop
            # preference must not request a resizable window there.
            self.fullscreen = True
        if screen_size is None:
            display_info = pygame.display.Info()
            screen_size = (display_info.current_w, display_info.current_h)
        self.windowed_size = screen_size
        self.screen = self.apply_display_mode(headless=headless)
        self.init_mobile_runtime(safe_insets)
        if not headless:
            self.refresh_automatic_ui_scale()
        # Branded window/taskbar icon: the octahedron relic logo. Best-effort —
        # headless/dummy drivers and platforms without bundled assets quietly skip.
        icon_surface = load_icon(64)
        if icon_surface is not None:
            try:
                pygame.display.set_icon(icon_surface)
            except pygame.error:
                pass
        self.clock = pygame.time.Clock()
        self.frame_pacing = FramePacing(self.clock)
        # load_options() runs before the display/clock exists so graphics mode
        # can be selected before set_mode(). Apply its persisted cap now that
        # FramePacing exists; otherwise every normal startup silently uses 60
        # until the player changes the option again.
        self.frame_pacing.set_frame_rate_cap(self.frame_rate_cap)
        self.rebuild_fonts()
        self.ui_assets = UiAssetLibrary()
        self.sprites = SpriteAtlas(legacy_graphics=self.legacy_graphics)
        self.quest_cutscenes = load_quest_cutscene_library()
        self.active_cutscene: ActiveQuestCutscene | None = None
        # Completed cutscene narration can be reviewed line-by-line.
        # The renderer publishes the current overflow range; right-stick repeat
        # state stays transient and is never serialized.
        self.cutscene_narration_scroll = 0
        self.cutscene_narration_follow_tail = True
        self.cutscene_scroll_axis_direction = 0
        self.cutscene_scroll_axis_repeat = 0.0
        self.tile_cache: dict[
            tuple[
                str,
                int,
                int,
                bool,
                bool,
                bool,
                bool,
                str | None,
                str | None,
            ],
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
        # 4.2.2: scroll offset (in wrapped lines) for the quest info panel's
        # story text. The renderer clamps it against the current overflow and
        # publishes `_story_panel_scroll_max` / `_story_panel_visible_lines`.
        self.story_panel_scroll = 0
        # 4.3.17 WS-G: scroll offset (in wrapped lines) for the About screen's
        # Open Source Licenses section. The renderer publishes
        # `_licenses_scroll_max` / `_licenses_visible_lines` each draw.
        self.licenses_scroll = 0
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
        self.exit_confirmation_cursor = self.EXIT_CONFIRMATION_CANCEL
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
        self.reset_friendly_npc_runtime()
        # Persistent Acolyte/Ranger familiars. Reset on restart or floor descent
        # and serialized additively (old saves load with none).
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
        self.enemy_hit_flash_durations: dict[int, float] = {}
        self.player_hit_flash = 0.0
        self.player_hit_flash_duration = 0.0
        self.player_action_state = ""
        self.player_action_ttl = 0.0
        self.player_action_elapsed = 0.0
        self.player_action_duration = 0.0
        # 4.2: garden-room passive healing glow. ``garden_heal_accumulator``
        # banks time until the next +HP tick while standing inside a garden
        # flavor room, and ``garden_heal_glow`` is a transient visual timer
        # the renderer fades a greenish aura from after each tick.
        self.garden_heal_accumulator = 0.0
        self.garden_heal_glow = 0.0
        self.garden_heal_glow_duration = 0.0
        self.ambient_overlay_cache: dict[tuple[int, int, str, int], pygame.Surface] = {}
        self.audio = AudioSystem()
        self.audio_available = self.audio.initialize(headless)
        self._options_visible_range: tuple[int, int] = (0, 0)
        self._options_row_viewport = pygame.Rect(0, 0, 0, 0)
        self._options_selected_row_rect = pygame.Rect(0, 0, 0, 0)
        self._options_row_font_height = 0
        # Render-published hitboxes consumed by mouse and touch input. Keeping
        # them initialized prevents stale context data before the first draw.
        self._menu_row_rects: tuple[pygame.Rect, ...] = ()
        self._title_row_rects: tuple[pygame.Rect, ...] = ()
        self._controls_keyboard_row_rects: tuple[pygame.Rect, ...] = ()
        self._controls_gamepad_row_rects: tuple[pygame.Rect, ...] = ()
        self._inventory_visible_row_rects: list[pygame.Rect] = []
        self._inventory_sort_mode_rects: list[tuple[str, pygame.Rect]] = []
        self._shop_visible_start = 0
        self._shop_visible_row_rects: list[pygame.Rect] = []
        self._shop_mode_rects: tuple[pygame.Rect, ...] = ()
        self._character_tab_rects: tuple[pygame.Rect, ...] = ()
        self._cutscene_choice_rects: list[pygame.Rect] = []
        self._story_intro_choice_rects: list[pygame.Rect] = []
        # 4.6 multiplayer session driver + shared single-line text entry.
        self.text_input = None
        self.init_net()
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
        # Colors may arrive as lists (e.g. from JSON-restored enemy.state on
        # older save paths). The draw_impact overlay cache builds a hashable
        # tuple key that includes ``color``, so normalize once at the entry point
        # to keep ImpactEffect.color a tuple regardless of the caller.
        if not isinstance(color, tuple):
            color = (int(color[0]), int(color[1]), int(color[2]))
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
        # 4.6: while the host simulates a network partner's action, the pose
        # belongs to that actor, not the shared local-player visual globals.
        acting = getattr(self, "player", None)
        if (
            self.mp_active
            and acting is not None
            and acting.player_id != self.local_player_id
        ):
            if state != acting.action_state or acting.action_ttl <= 0.0:
                acting.action_elapsed = 0.0
                acting.action_duration = ttl
            else:
                acting.action_duration = max(
                    acting.action_duration, acting.action_elapsed + ttl
                )
            acting.action_state = state
            acting.action_ttl = max(acting.action_ttl, ttl)
            return
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
        self.enemy_hit_flash_durations = {}
        self.player_hit_flash = 0.0
        self.player_hit_flash_duration = 0.0
        self.player_action_state = ""
        self.player_action_ttl = 0.0
        self.player_action_elapsed = 0.0
        self.player_action_duration = 0.0
        # 4.2: garden healing glow is transient and clears with the rest of
        # the visual state on floor transitions / cutscenes / load.
        self.garden_heal_accumulator = 0.0
        self.garden_heal_glow = 0.0
        self.garden_heal_glow_duration = 0.0
        # Story text scroll positions reset with the visual/story context.
        self.story_panel_scroll = 0
        self.reset_active_cutscene_narration_scroll()
        # Milestone 3.16 - transient light pulses are visual effects too.
        self.lights = []

    def update_visual_effects(
        self, dt: float, *, advance_actor_clocks: bool = True
    ) -> None:
        if self.impact_effects:
            for effect in self.impact_effects:
                effect.update(dt)
            self.impact_effects = [
                effect for effect in self.impact_effects if effect.ttl > 0
            ]
        # Milestone 3.16 - decay transient light pulses (skill casts,
        # projectile trails, impact flares) alongside impacts and slashes.
        self.update_lights(dt)
        self.screen_flash_ttl = max(0.0, self.screen_flash_ttl - dt)
        if advance_actor_clocks:
            self.player_hit_flash = max(0.0, self.player_hit_flash - dt)
            if self.player_hit_flash <= 0.0:
                self.player_hit_flash_duration = 0.0
            if self.player_action_ttl > 0.0:
                self.player_action_elapsed += dt
            self.player_action_ttl = max(0.0, self.player_action_ttl - dt)
            if self.player_action_ttl <= 0:
                self.player_action_state = ""
                self.player_action_elapsed = 0.0
                self.player_action_duration = 0.0
            # 4.2: fade the garden healing aura alongside other transient
            # player visuals so it decays even when the player steps out of
            # the garden between ticks.
            self.garden_heal_glow = max(0.0, self.garden_heal_glow - dt)
            if self.garden_heal_glow <= 0.0:
                self.garden_heal_glow_duration = 0.0
            if self.enemy_hit_flashes:
                alive_enemy_ids = {id(enemy) for enemy in self.enemies}
                self.enemy_hit_flashes = {
                    enemy_id: max(0.0, ttl - dt)
                    for enemy_id, ttl in self.enemy_hit_flashes.items()
                    if ttl - dt > 0 and enemy_id in alive_enemy_ids
                }
                self.enemy_hit_flash_durations = {
                    enemy_id: duration
                    for enemy_id, duration in self.enemy_hit_flash_durations.items()
                    if enemy_id in self.enemy_hit_flashes
                }
            elif self.enemy_hit_flash_durations:
                self.enemy_hit_flash_durations.clear()
        if self.slashes:
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
        # Rebind the pacing clock each run in case a caller (or test) swapped
        # ``self.clock`` after construction. ``Game.run()`` is still the only
        # caller of ``clock.tick`` (via frame_pacing).
        self.frame_pacing._clock = self.clock
        while self.running:
            performance = getattr(self, "_mobile_performance_monitor", None)
            if performance is not None:
                performance.begin_frame(self)

            suspended = self.mobile_mode and self.mobile_suspended
            started = time.perf_counter()
            dt = self.frame_pacing.tick(suspended=suspended)
            if performance is not None:
                performance.record_phase("tick", time.perf_counter() - started)
            self.ui_elapsed += dt

            # 4.6 multiplayer pump: after the frame tick, before any
            # state-dependent work. Cheap two-attribute check when no client
            # exists; while Android is suspended outbound traffic pauses and
            # the socket is held (NetMixin.poll early-outs).
            if not suspended:
                self.poll()

            started = time.perf_counter()
            self.handle_events()
            if performance is not None:
                performance.record_phase("events", time.perf_counter() - started)
            if self.mobile_mode and self.mobile_suspended:
                if performance is not None:
                    performance.finish_frame(self)
                continue

            if self.state == "playing":
                started = time.perf_counter()
                self.update(dt)
                if performance is not None:
                    performance.record_phase("update", time.perf_counter() - started)
            self.draw()
            if performance is not None:
                performance.finish_frame(self)
        self.release_mobile_gpu_renderer()
        pygame.quit()

    def request_exit_confirmation(self) -> None:
        if self.mobile_mode:
            self.cancel_mobile_touches()
            self.mobile_hub_open = False
            self.quest_info_visible = False
        if self.state != "confirm_exit":
            self.exit_previous_state = self.state
            self.exit_confirmation_cursor = self.EXIT_CONFIRMATION_CANCEL
            self.last_save_error = ""
        self.show_help = False
        self.character_menu_open = False
        self.state = "confirm_exit"

    def move_exit_confirmation_cursor(self, direction: int) -> None:
        self.exit_confirmation_cursor = (
            self.exit_confirmation_cursor + (1 if direction > 0 else -1)
        ) % self.EXIT_CONFIRMATION_OPTION_COUNT

    def activate_exit_confirmation_selection(self) -> None:
        if self.exit_confirmation_cursor == self.EXIT_CONFIRMATION_EXIT:
            self.confirm_exit()
        elif self.exit_confirmation_cursor == self.EXIT_CONFIRMATION_MAIN_MENU:
            self.return_to_main_menu()
        else:
            self.cancel_exit_confirmation()

    def return_to_main_menu(self) -> None:
        # A multiplayer session ends with a final `bye` and never writes or
        # deletes the single-player run save.
        if self.mp_active or self.mp_session is not None:
            self.mp_shutdown(send_bye=True)
        elif self.exit_previous_state == "playing" and not self.save_run():
            return
        if self.mobile_mode:
            self.resume_mobile_audio_focus()
        self.show_help = False
        self.inventory_open = False
        self.character_menu_open = False
        self.mobile_hub_open = False
        self.quest_info_visible = False
        self.close_shop()
        self.state = "title"
        self.exit_previous_state = "title"

    def cancel_exit_confirmation(self) -> None:
        self.state = self.exit_previous_state or "title"
        if self.mobile_mode:
            self.resume_mobile_audio_focus()

    def confirm_exit(self) -> None:
        if self.mp_active or self.mp_session is not None:
            self.mp_shutdown(send_bye=True)
        elif self.exit_previous_state == "playing" and not self.save_run():
            return
        self.running = False

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if self.handle_mobile_lifecycle_event(event):
                continue
            if self.handle_mobile_finger_event(event):
                continue
            # 4.6: the shared text-entry field (player name, join code, server
            # host/port) consumes typing before any state hotkeys can fire.
            if self.handle_text_input_event(event):
                continue
            if event.type == pygame.QUIT:
                self.request_exit_confirmation()
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.windowed_size = (max(640, event.w), max(480, event.h))
                self.screen = pygame.display.set_mode(
                    self.windowed_size, pygame.RESIZABLE
                )
                self._mobile_layout_cache = None
                self.refresh_mobile_safe_insets()
                self.refresh_automatic_ui_scale()
            elif event.type == pygame.WINDOWDISPLAYCHANGED:
                self._mobile_layout_cache = None
                self.refresh_mobile_safe_insets()
                self.refresh_automatic_ui_scale()
            elif self.handle_controller_event(event):
                continue
            elif event.type == pygame.KEYDOWN:
                if event.key == getattr(pygame, "K_AC_BACK", -1):
                    self._dispatch_command(Command.BACK)
                elif self.state == "confirm_exit":
                    if event.key in (pygame.K_UP, pygame.K_LEFT):
                        self.move_exit_confirmation_cursor(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                        self.move_exit_confirmation_cursor(1)
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self.activate_exit_confirmation_selection()
                    elif event.key == pygame.K_y:
                        self.confirm_exit()
                    elif event.key == pygame.K_m:
                        self.return_to_main_menu()
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
                    elif self.state == "mp_setup":
                        self.mp_back_from_setup_step()
                    elif self.state == "mp_lobby":
                        self.mp_leave_lobby()
                    else:
                        self.request_exit_confirmation()
                elif (
                    self.state == "playing"
                    and event.key == pygame.K_d
                    and event.mod & pygame.KMOD_CTRL
                    and event.mod & pygame.KMOD_SHIFT
                ):
                    self.toggle_current_floor_dark()
                elif (
                    event.key == pygame.K_l
                    and event.mod & pygame.KMOD_CTRL
                    and event.mod & pygame.KMOD_ALT
                ):
                    # In-game legacy graphics toggle. Works in every state so
                    # players can flip rendering mode without entering Options.
                    # Placed before the state-specific branches so it intercepts
                    # the K_l shortcuts used on the title and options menus.
                    self.set_legacy_graphics(not self.legacy_graphics)
                    if self.state == "playing" and hasattr(self, "player"):
                        self.floaters.append(
                            FloatingText(
                                "Legacy graphics"
                                if self.legacy_graphics
                                else "Asset sprites",
                                self.player.x,
                                self.player.y - 0.5,
                                self.theme.accent,
                                ttl=1.4,
                            )
                        )
                elif self.state == "title":
                    # Five title rows: 0=One will descend, 1=Two will descend,
                    # 2=Resume, 3=Options, 4=About. Resume is only selectable
                    # when a save exists.
                    if event.key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_s):
                        self.title_selection = self._next_title_selection(1)
                    elif event.key in (pygame.K_UP, pygame.K_LEFT, pygame.K_w):
                        self.title_selection = self._next_title_selection(-1)
                    elif event.key == pygame.K_RETURN:
                        self._activate_title_selection()
                    elif event.key == pygame.K_n:
                        self.state = "archetype_select"
                    elif event.key == pygame.K_t:
                        self.start_mp_setup()
                    elif event.key in (pygame.K_l, pygame.K_r) and self.save_exists():
                        self.load_run()
                    elif event.key == pygame.K_o:
                        self.state = "options"
                    elif event.key in (pygame.K_a, pygame.K_c):
                        self.state = "about"
                        self.licenses_scroll = 0
                    elif event.key in (pygame.K_h, pygame.K_SLASH):
                        self.state = "about"
                        self.licenses_scroll = 0
                elif self.state == "mp_setup":
                    if event.key == pygame.K_BACKSPACE:
                        self.mp_back_from_setup_step()
                    elif self.mp_setup_step == "role":
                        if event.key in (
                            pygame.K_UP,
                            pygame.K_DOWN,
                            pygame.K_LEFT,
                            pygame.K_RIGHT,
                            pygame.K_w,
                            pygame.K_s,
                        ):
                            self.mp_setup_role_cursor = (
                                self.mp_setup_role_cursor + 1
                            ) % 2
                        elif event.key in (pygame.K_RETURN, pygame.K_e):
                            self.mp_choose_role(self.mp_setup_role_cursor == 0)
                        elif event.key == pygame.K_h:
                            self.mp_choose_role(True)
                        elif event.key == pygame.K_j:
                            self.mp_choose_role(False)
                    elif self.mp_setup_step == "host_code":
                        if event.key in (pygame.K_RETURN, pygame.K_e):
                            self.mp_begin_hosting()
                        elif event.key == pygame.K_r:
                            self.mp_regenerate_host_code()
                elif self.state == "mp_lobby":
                    session = self.mp_session
                    ready = bool(session is not None and session.local_ready)
                    if event.key == pygame.K_BACKSPACE:
                        self.mp_leave_lobby()
                    elif not ready and event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                        index = (
                            ARCHETYPES.index(self.selected_archetype) + 1
                        ) % len(ARCHETYPES)
                        self.selected_archetype = ARCHETYPES[index]
                    elif not ready and event.key in (pygame.K_LEFT, pygame.K_UP):
                        index = (
                            ARCHETYPES.index(self.selected_archetype) - 1
                        ) % len(ARCHETYPES)
                        self.selected_archetype = ARCHETYPES[index]
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self.mp_lobby_send_ready()
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
                        self._activate_options_row(
                            self.OPTIONS_ROW_FULLSCREEN, True
                        )
                    elif event.key == pygame.K_d:
                        self.options_cursor = self.OPTIONS_ROW_DIFFICULTY
                        self.cycle_difficulty()
                    elif event.key in (pygame.K_0, pygame.K_KP0):
                        self.options_cursor = self.OPTIONS_ROW_UI_SCALE
                        self.enable_automatic_ui_scale()
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
                        pygame.K_o,
                    ):
                        self.state = "title"
                    elif event.key in (pygame.K_UP, pygame.K_LEFT):
                        self.scroll_licenses(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_RIGHT):
                        self.scroll_licenses(1)
                    elif event.key == pygame.K_PAGEUP:
                        page = max(1, int(getattr(self, "_licenses_visible_lines", 3)) - 1)
                        self.scroll_licenses(-page)
                    elif event.key == pygame.K_PAGEDOWN:
                        page = max(1, int(getattr(self, "_licenses_visible_lines", 3)) - 1)
                        self.scroll_licenses(page)
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
                    if event.key in (
                        pygame.K_UP,
                        pygame.K_DOWN,
                        pygame.K_LEFT,
                        pygame.K_RIGHT,
                    ):
                        cmd = key_command(event.key, event.mod)
                        if cmd is not None:
                            self._dispatch_command(cmd)
                    elif event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                        page = max(
                            1,
                            getattr(
                                self,
                                "_cutscene_narration_visible_lines",
                                3,
                            )
                            - 1,
                        )
                        self.scroll_active_cutscene_narration(
                            -page if event.key == pygame.K_PAGEUP else page
                        )
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        choice_index = event.key - pygame.K_1
                        visible_choice_count = min(
                            9, len(self.active_cutscene_choices())
                        )
                        if choice_index < visible_choice_count:
                            self.cutscene_cursor = choice_index
                            self.choose_active_cutscene_option(choice_index)
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self._dispatch_command(Command.CONFIRM)
                    elif event.key == pygame.K_SPACE:
                        if not self.advance_active_cutscene():
                            self.floaters.append(
                                FloatingText(
                                    "Use arrows + Enter/E, or 1-3, to answer",
                                    self.player.x,
                                    self.player.y - 0.5,
                                    self.story_state.accent
                                    if self.story_state
                                    else self.theme.accent,
                                    ttl=1.0,
                                )
                            )
                elif self.state == "playing" and self.story_intro_pending:
                    if event.key in (
                        pygame.K_UP,
                        pygame.K_DOWN,
                        pygame.K_LEFT,
                        pygame.K_RIGHT,
                    ):
                        cmd = key_command(event.key, event.mod)
                        if cmd is not None:
                            self._dispatch_command(cmd)
                    elif pygame.K_1 <= event.key <= pygame.K_3:
                        self.cutscene_cursor = event.key - pygame.K_1
                        self.choose_story_relic_path(self.cutscene_cursor)
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self._dispatch_command(Command.CONFIRM)
                    elif event.key == pygame.K_SPACE:
                        self.floaters.append(
                            FloatingText(
                                "Use arrows + Enter/E, or 1-3, to bind the relic",
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
                    if self.mp_active:
                        # A finished co-op run returns to the title; restarting
                        # a new descent is a single-player entry point.
                        self.mp_end_session_to_title("")
                    else:
                        self.show_help = False
                        self.inventory_open = False
                        self.character_menu_open = False
                        self.state = "archetype_select"
                elif event.key == pygame.K_e and self.state == "playing":
                    self.interact()
                elif event.key == pygame.K_q and self.state == "playing":
                    self.toggle_quest_info_visibility()
                elif (
                    event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN)
                    and self.state == "playing"
                    and self.quest_info_visible
                    and not self.character_menu_open
                ):
                    # 4.2.2: PgUp/PgDn page the quest info panel's story text
                    # by one panel of lines. The inventory and shop branches
                    # above consume these keys while their overlays are open.
                    page = max(
                        1, getattr(self, "_story_panel_visible_lines", 3) - 1
                    )
                    self.scroll_story_panel(
                        -page if event.key == pygame.K_PAGEUP else page
                    )
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
                and not getattr(event, "touch", False)
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
            elif (
                event.type == pygame.MOUSEWHEEL
                and self.state == "playing"
                and self.active_cutscene is not None
            ):
                # Completed narration can be reviewed without disturbing the
                # choice cursor. Ctrl+wheel zoom retains priority above.
                self.scroll_active_cutscene_narration(-event.y * 2)
            elif (
                event.type == pygame.MOUSEWHEEL
                and self.state == "playing"
                and self.quest_info_visible
                and not self.inventory_open
                and not self.character_menu_open
                and not self.shop_open
                and self.active_cutscene is None
                and not self.story_intro_pending
            ):
                # 4.2.2: plain scroll wheel pages the quest info panel's story
                # text (Ctrl+scroll above still zooms the viewport). Scroll up
                # shows earlier lines.
                self.scroll_story_panel(-event.y * 2)
            elif (
                event.type == pygame.MOUSEMOTION
                and not getattr(event, "touch", False)
                and self.state == "playing"
            ):
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
        if self.mobile_mode and self.mobile_suspended:
            return
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
        if self.mp_is_joiner():
            # The joiner never runs AI/RNG/combat simulation: it renders the
            # latest authoritative snapshot, smooths actors, and sends input
            # intents (NetMixin.poll handles the outbound cadence).
            self.mp_update_joiner(dt)
            return
        menu_pauses_simulation = bool(
            self.active_cutscene is None
            and not self.story_intro_pending
            and (
                self.inventory_open
                or self.character_menu_open
                or self.shop_open
                or (
                    self.mobile_mode
                    and (
                        self.show_help
                        or self.mobile_hub_open
                        or self.quest_info_visible
                    )
                )
            )
        )
        self.update_visual_effects(
            dt, advance_actor_clocks=not menu_pauses_simulation
        )
        if self.active_cutscene is not None:
            self.update_active_cutscene_scroll_input(dt)
            self.update_active_cutscene(dt)
            self.update_floaters(dt)
            return
        # Validate the shopkeeper is still present and in range. This may close
        # a stale shop, but the simulation should still pause for this frame.
        shop_was_open = self.shop_open
        if self.shop_open:
            if self.active_shopkeeper not in self.shopkeepers:
                self.close_shop()
            elif self.active_shopkeeper is not None:
                shop_dx = self.active_shopkeeper.x - self.player.x
                shop_dy = self.active_shopkeeper.y - self.player.y
                if shop_dx * shop_dx + shop_dy * shop_dy > 2.6 * 2.6:
                    self.close_shop()
        if self.story_intro_pending:
            self.update_floaters(dt)
            return
        # Opening a full-screen mobile overlay pauses the run. Desktop keeps its
        # established help behavior; inventory, character, and shop always pause.
        if self.inventory_open or self.character_menu_open or self.shop_open or shop_was_open or (
            self.mobile_mode
            and (
                self.show_help
                or self.mobile_hub_open
                or self.quest_info_visible
            )
        ):
            self.update_floaters(dt)
            return
        # Sample before update_player() decrements Time Skip so final partial and
        # overlapping slow intervals are integrated consistently at every FPS.
        # In co-op, either player's Time Skip slows the shared enemy simulation.
        time_skip_remaining = max(
            (p.time_skip_timer for p in self.active_players()),
            default=self.player.time_skip_timer,
        )
        enemy_time_scale = self.enemy_time_scale(
            dt, remaining=time_skip_remaining
        )
        self.update_player_aim()
        if not (self.mp_active and self.player.hp <= 0):
            self.update_player(dt)
        self.mp_apply_remote_intents(dt)
        self.update_friendly_npcs(dt)
        self.update_camera(dt)
        self.update_revealed_tiles()
        self.update_enemy_statuses(
            dt, time_skip_remaining=time_skip_remaining
        )
        self.update_ambush_bells(dt)
        self.update_enemies(
            dt,
            time_scale=enemy_time_scale,
            time_skip_remaining=time_skip_remaining,
        )
        self.update_ambush_bells(0.0)
        self.update_familiars(dt)
        self.update_projectiles(dt)
        self.update_traps(dt)
        self.update_secrets()
        self.update_boss_encounter()
        self.update_floaters(dt)
        self.advance_animation_phases(dt)

        if self.mp_active:
            # Co-op has no revive: a fallen player spectates, and the shared
            # run ends only when no player remains alive. The host is the sole
            # authority for the outcome and announces it to the joiner.
            if (
                self.state == "playing"
                and not any(p.hp > 0 for p in self.active_players())
            ):
                if not self.run_stats.cause_of_death:
                    self.run_stats.cause_of_death = "unknown dungeon violence"
                self.ambush_bells = []
                self.finalize_run("death")
                self.state = "dead"
                self.audio.stop_music()
                self.play_sfx("death")
                self.mp_notify_run_ended("death")
        elif self.player.hp <= 0 and self.state == "playing":
            if not self.run_stats.cause_of_death:
                self.run_stats.cause_of_death = "unknown dungeon violence"
            self.ambush_bells = []
            self.finalize_run("death")
            self.state = "dead"
            self.audio.stop_music()
            self.play_sfx("death")
            self.delete_save()

    def update_secrets(self) -> None:
        players = self.active_players()
        for secret in self.secrets:
            if secret.revealed or secret.opened:
                continue
            for player in players:
                dx = secret.x - player.x
                dy = secret.y - player.y
                if dx * dx + dy * dy < 1.55 * 1.55:
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
                    break

    def update_floaters(self, dt: float) -> None:
        for floater in self.floaters:
            floater.update(dt)
        self.floaters = [floater for floater in self.floaters if floater.ttl > 0]


def main() -> None:
    Game().run()
