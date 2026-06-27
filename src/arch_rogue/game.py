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
    BOSS_HIT_RADIUS as BOSS_HIT_RADIUS,
)
from .constants import (
    DARK_LEVEL_LIGHT_RADIUS as DARK_LEVEL_LIGHT_RADIUS,
)
from .constants import (
    DUNGEON_DEPTH,
    FPS,
    UI_SCALE,
)
from .constants import (
    ENEMY_HIT_RADIUS as ENEMY_HIT_RADIUS,
)
from .constants import (
    ENEMY_PROJECTILE_HIT_RADIUS as ENEMY_PROJECTILE_HIT_RADIUS,
)
from .constants import (
    LARGE_ENEMY_HIT_RADIUS as LARGE_ENEMY_HIT_RADIUS,
)
from .constants import (
    MAX_INVENTORY as MAX_INVENTORY,
)
from .constants import (
    PLAYER_HIT_RADIUS as PLAYER_HIT_RADIUS,
)
from .constants import (
    PLAYER_MELEE_ARC_DOT as PLAYER_MELEE_ARC_DOT,
)
from .constants import (
    PLAYER_MELEE_RANGE as PLAYER_MELEE_RANGE,
)
from .constants import (
    PLAYER_PROJECTILE_HIT_RADIUS as PLAYER_PROJECTILE_HIT_RADIUS,
)
from .constants import (
    WALK_ANIMATION_RATE as WALK_ANIMATION_RATE,
)
from .constants import (
    SlashEffect as SlashEffect,
)
from .content import (
    ARCHETYPES,
    DEFAULT_DIFFICULTY_NAME,
    DUNGEON_THEMES,
    RARITY_PROFILES,
    RUN_MODIFIERS,
    SKILL_UPGRADES,
)
from .content import (
    ARMOR_DEFINITIONS as ARMOR_DEFINITIONS,
)
from .content import (
    BOSS_DEFINITIONS as BOSS_DEFINITIONS,
)
from .content import (
    ELITE_MODIFIERS as ELITE_MODIFIERS,
)
from .content import (
    ENCOUNTER_TEMPLATES as ENCOUNTER_TEMPLATES,
)
from .content import (
    ENEMY_DEFINITIONS as ENEMY_DEFINITIONS,
)
from .content import (
    FINAL_ROOM_ENEMY_DEFINITIONS as FINAL_ROOM_ENEMY_DEFINITIONS,
)
from .content import (
    SECRET_TYPES as SECRET_TYPES,
)
from .content import (
    SHRINE_TYPES as SHRINE_TYPES,
)
from .content import (
    STORY_LOCATION_MOTIFS as STORY_LOCATION_MOTIFS,
)
from .content import (
    TRAP_DEFINITIONS as TRAP_DEFINITIONS,
)
from .content import (
    WEAPON_DEFINITIONS as WEAPON_DEFINITIONS,
)
from .content import (
    BossDefinition as BossDefinition,
)
from .content import (
    EncounterTemplate as EncounterTemplate,
)
from .content import (
    EnemyDefinition as EnemyDefinition,
)
from .dungeon import Dungeon as Dungeon
from .interactions import InteractionMixin
from .inventory import InventoryMixin
from .menus import MenuRenderer
from .models import (
    Archetype as Archetype,
)
from .models import (
    Color,
    FloatingText,
    FloorPlan,
    ImpactEffect,
    RunStats,
    Shopkeeper,
    StoryGuest,
    StoryState,
)
from .models import (
    Enemy as Enemy,
)
from .models import (
    Item as Item,
)
from .models import (
    Player as Player,
)
from .models import (
    Projectile as Projectile,
)
from .models import (
    Room as Room,
)
from .models import (
    SecretCache as SecretCache,
)
from .models import (
    Shrine as Shrine,
)
from .models import (
    Trap as Trap,
)
from .options import OptionsMixin
from .population import PopulationMixin
from .quest_assets import (
    ActiveQuestCutscene,
    load_quest_cutscene_library,
)
from .quest_assets import (
    RuntimeDialogueChoice as RuntimeDialogueChoice,
)
from .quest_assets import (
    format_asset_text as format_asset_text,
)
from .rendering import RenderingMixin
from .run_flow import RunFlowMixin
from .save_system import SaveLoadMixin
from .shop import ShopMixin
from .sprites import PixelSpriteAtlas
from .story import (
    StoryEngine as StoryEngine,
)
from .story import (
    clamp_story_effect as clamp_story_effect,
)
from .story import (
    record_story_choice as record_story_choice,
)
from .story import (
    record_unanswered_story_beat as record_unanswered_story_beat,
)
from .story import (
    story_beat_for_depth as story_beat_for_depth,
)
from .story import (
    story_beat_index_for_depth as story_beat_index_for_depth,
)
from .story import (
    story_effect as story_effect,
)
from .story import (
    story_guest_from_beat as story_guest_from_beat,
)
from .story_runtime import StoryRuntimeMixin


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
        self.difficulty_name = DEFAULT_DIFFICULTY_NAME
        self.hell_unlocked = False
        self.hell_unlocked_this_run = False
        self.meta_progress: dict[str, Any] = self.default_meta_progress()
        self.run_history: list[dict[str, Any]] = []
        self.last_save_error = ""
        self.last_load_error = ""
        self.screen_flash_ttl = 0.0
        self.screen_flash_color: Color = (0, 0, 0)
        self.load_options()
        if screen_size is None:
            display_info = pygame.display.Info()
            screen_size = (display_info.current_w, display_info.current_h)
        self.windowed_size = screen_size
        self.screen = self.apply_display_mode(headless=headless)
        self.clock = pygame.time.Clock()
        self.rebuild_fonts()
        self.sprites = PixelSpriteAtlas()
        self.quest_cutscenes = load_quest_cutscene_library()
        self.active_cutscene: ActiveQuestCutscene | None = None
        self.tile_cache: dict[
            tuple[str, int, int], tuple[pygame.Surface, int, int]
        ] = {}
        self.rng = random.Random()
        self.running = True
        self.inventory_open = False
        self.inventory_sort_mode = "type"
        self.inventory_cursor = 0
        self.inventory_scroll = 0
        self.character_menu_open = False
        self.shop_open = False
        self.active_shopkeeper: Shopkeeper | None = None
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.show_help = False
        self.quest_info_visible = False
        self.run_stats = RunStats()
        self.state = "archetype_select"
        self.elapsed = 0.0
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
        self.story_seed = 0
        self.story_state: StoryState | None = None
        self.story_guests: list[StoryGuest] = []
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
        self.ambient_overlay_cache: dict[tuple[int, int, str, int], pygame.Surface] = {}
        self.audio = AudioSystem()
        self.audio_available = self.audio.initialize(headless)
        self.menus = MenuRenderer(self, ARCHETYPES, DUNGEON_DEPTH)

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
    ) -> None:
        self.impact_effects.append(ImpactEffect(x, y, color, ttl, radius, kind, ttl))

    def set_player_action_visual(self, state: str, ttl: float = 0.18) -> None:
        self.player_action_state = state
        self.player_action_ttl = max(self.player_action_ttl, ttl)

    def reset_transient_visuals(self) -> None:
        self.enemy_hit_flashes = {}
        self.player_hit_flash = 0.0
        self.player_action_state = ""
        self.player_action_ttl = 0.0

    def update_visual_effects(self, dt: float) -> None:
        for effect in self.impact_effects:
            effect.update(dt)
        self.impact_effects = [
            effect for effect in self.impact_effects if effect.ttl > 0
        ]
        self.screen_flash_ttl = max(0.0, self.screen_flash_ttl - dt)
        self.player_hit_flash = max(0.0, self.player_hit_flash - dt)
        self.player_action_ttl = max(0.0, self.player_action_ttl - dt)
        if self.player_action_ttl <= 0:
            self.player_action_state = ""
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

    def acquired_skill_upgrades(self) -> list[tuple[str, str]]:
        by_key = {upgrade.key: upgrade for upgrade in SKILL_UPGRADES}
        return [
            (by_key[key].name, by_key[key].description)
            for key in self.player.skill_upgrades
            if key in by_key
        ]

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
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
                    if event.key in (pygame.K_RETURN, pygame.K_n):
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
                        self.audio_enabled = not self.audio_enabled
                        self.save_options()
                    elif event.key == pygame.K_m:
                        self.music_enabled = not self.music_enabled
                        self.sync_music()
                        self.save_options()
                    elif event.key == pygame.K_f:
                        if not self.fullscreen:
                            self.windowed_size = self.screen.get_size()
                        self.fullscreen = not self.fullscreen
                        self.screen = self.apply_display_mode()
                        self.save_options()
                    elif event.key == pygame.K_d:
                        self.cycle_difficulty()
                    elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                        self.ui_scale = min(4, self.ui_scale + 1)
                        self.rebuild_fonts()
                        self.save_options()
                    elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                        self.ui_scale = max(1, self.ui_scale - 1)
                        self.rebuild_fonts()
                        self.save_options()
                    elif event.key in (pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_o):
                        self.state = "title"
                elif self.state == "about":
                    if event.key in (
                        pygame.K_RETURN,
                        pygame.K_BACKSPACE,
                        pygame.K_a,
                        pygame.K_h,
                    ):
                        self.state = "title"
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
                elif event.key == pygame.K_r and self.state == "playing":
                    self.use_first_potion()
                elif event.key == pygame.K_t and self.state == "playing":
                    self.use_first_mana_potion()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self.update_player_aim()
                    self.player_melee_attack()
                elif event.key == pygame.K_f and self.state == "playing":
                    self.update_player_aim()
                    self.player_cast_bolt()
                elif event.key == pygame.K_c and self.state == "playing":
                    self.character_menu_open = not self.character_menu_open
                    if self.character_menu_open:
                        self.inventory_open = False
                        self.close_shop()
                elif event.key == pygame.K_v and self.state == "playing":
                    self.update_player_aim()
                    self.player_cast_nova()
                elif event.key == pygame.K_LCTRL and self.state == "playing":
                    self.update_player_aim()
                    self.player_dash()
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
                        self.player_cast_nova()
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
                if event.button == 1:
                    self.face_player_toward_screen_point(*event.pos)
                    if self.enemy_in_melee_arc():
                        self.player_melee_attack()

    def update(self, dt: float) -> None:
        self.elapsed += dt
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
        self.update_player_aim()
        self.update_player(dt)
        self.update_enemy_statuses(dt)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_traps(dt)
        self.update_secrets()
        self.update_floaters(dt)

        if self.player.hp <= 0 and self.state == "playing":
            if not self.run_stats.cause_of_death:
                self.run_stats.cause_of_death = "unknown dungeon violence"
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
