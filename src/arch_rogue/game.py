from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path
from typing import Any

import pygame

from . import __version__
from .audio import AudioSystem, MusicProfile
from .constants import (
    BOSS_HIT_RADIUS,
    DUNGEON_DEPTH,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    FPS,
    LARGE_ENEMY_HIT_RADIUS,
    MAX_INVENTORY,
    PLAYER_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
    PLAYER_PROJECTILE_HIT_RADIUS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_H,
    TILE_W,
    UI_SCALE,
    WALK_ANIMATION_RATE,
    SlashEffect,
)
from .content import (
    ARCHETYPES,
    ARMOR_DEFINITIONS,
    DEFAULT_DIFFICULTY_NAME,
    DIFFICULTY_PROFILES,
    DUNGEON_THEMES,
    ELITE_MODIFIERS,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    HELL_DIFFICULTY_NAME,
    RARITY_PROFILES,
    RUN_MODIFIERS,
    SECRET_HINTS,
    SECRET_TYPES,
    SHRINE_HINTS,
    SHRINE_TYPES,
    SKILL_UPGRADES,
    STORY_LOCATION_MOTIFS,
    TRAP_DEFINITIONS,
    TRAP_HINTS,
    WEAPON_DEFINITIONS,
    DifficultyProfile,
    EnemyDefinition,
    InteractionHint,
)
from .dungeon import MAP_H, MAP_W, Dungeon
from .menus import MenuRenderer
from .models import (
    Archetype,
    Color,
    Enemy,
    FloatingText,
    ImpactEffect,
    Item,
    Player,
    Projectile,
    RunStats,
    SecretCache,
    Shrine,
    StoryGuest,
    StoryState,
    Trap,
)
from .quest_assets import (
    ActiveQuestCutscene,
    RuntimeDialogueChoice,
    format_asset_text,
    load_quest_cutscene_library,
)
from .rendering import RenderingMixin
from .save_system import SaveLoadMixin
from .sprites import PixelSpriteAtlas
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


class Game(SaveLoadMixin, RenderingMixin):
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
        self.show_help = False
        self.quest_info_visible = True
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

    def display_size(self) -> tuple[int, int]:
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return sizes[0]
        except pygame.error:
            pass
        display_info = pygame.display.Info()
        return display_info.current_w, display_info.current_h

    def apply_display_mode(self, headless: bool = False) -> pygame.Surface:
        if headless:
            return pygame.display.set_mode(self.windowed_size, pygame.HIDDEN)
        if self.fullscreen:
            # Use SDL's scaled fullscreen path so the game surface is expanded to
            # the actual monitor instead of being placed unscaled in the top-left
            # when the requested logical size differs from the desktop mode.
            return pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED
            )
        return pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def rebuild_fonts(self) -> None:
        self.tiny_font = pygame.font.Font(None, 14 * self.ui_scale)
        self.small_font = pygame.font.Font(None, 16 * self.ui_scale)
        self.font = pygame.font.Font(None, 22 * self.ui_scale)
        self.heading_font = pygame.font.Font(None, 32 * self.ui_scale)
        self.big_font = pygame.font.Font(None, 48 * self.ui_scale)
        self.title_font = pygame.font.Font(None, 62 * self.ui_scale)

    def available_difficulty_profiles(self) -> tuple[DifficultyProfile, ...]:
        return tuple(
            profile
            for profile in DIFFICULTY_PROFILES
            if self.hell_unlocked or profile.name != HELL_DIFFICULTY_NAME
        )

    def sanitize_difficulty_name(self, name: str) -> str:
        available_names = {
            profile.name for profile in self.available_difficulty_profiles()
        }
        if name in available_names:
            return name
        return DEFAULT_DIFFICULTY_NAME

    def difficulty_profile(self) -> DifficultyProfile:
        difficulty_name = self.sanitize_difficulty_name(self.difficulty_name)
        if difficulty_name != self.difficulty_name:
            self.difficulty_name = difficulty_name
        return next(
            profile
            for profile in DIFFICULTY_PROFILES
            if profile.name == self.difficulty_name
        )

    def cycle_difficulty(self) -> None:
        profiles = self.available_difficulty_profiles()
        if not profiles:
            self.difficulty_name = DEFAULT_DIFFICULTY_NAME
            self.save_options()
            return
        current_name = self.sanitize_difficulty_name(self.difficulty_name)
        current_index = next(
            (
                index
                for index, profile in enumerate(profiles)
                if profile.name == current_name
            ),
            0,
        )
        self.difficulty_name = profiles[(current_index + 1) % len(profiles)].name
        self.save_options()

    def unlock_hell_difficulty(self) -> bool:
        if self.hell_unlocked:
            return False
        self.hell_unlocked = True
        self.hell_unlocked_this_run = True
        self.save_options()
        return True

    def options_to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "audio_enabled": self.audio_enabled,
            "music_enabled": self.music_enabled,
            "fullscreen": self.fullscreen,
            "ui_scale": self.ui_scale,
            "difficulty": self.difficulty_profile().name,
            "hell_unlocked": self.hell_unlocked,
        }

    def load_options(self) -> bool:
        try:
            data = json.loads(self.options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        try:
            self.audio_enabled = bool(data.get("audio_enabled", True))
            self.music_enabled = bool(data.get("music_enabled", False))
            self.fullscreen = bool(data.get("fullscreen", False))
            self.ui_scale = max(1, min(4, int(data.get("ui_scale", UI_SCALE))))
            self.hell_unlocked = bool(data.get("hell_unlocked", False))
            self.difficulty_name = self.sanitize_difficulty_name(
                str(data.get("difficulty", DEFAULT_DIFFICULTY_NAME))
            )
        except (TypeError, ValueError):
            return False
        return True

    def save_options(self) -> bool:
        try:
            self.options_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(f"{self.options_path}.tmp")
            tmp_path.write_text(
                json.dumps(self.options_to_dict(), indent=2), encoding="utf-8"
            )
            tmp_path.replace(self.options_path)
        except (OSError, TypeError, ValueError):
            return False
        return True

    def current_music_profile(self) -> MusicProfile | None:
        if self.state in (
            "title",
            "options",
            "about",
            "archetype_select",
            "confirm_exit",
        ):
            return MusicProfile(
                0xA11CE,
                "Menu",
                "Main Menu",
                "Quiet",
                depth=0,
                mood="menu",
            )
        if self.state not in ("playing", "dead", "victory") or self.run_music_seed <= 0:
            return None
        return MusicProfile(
            self.run_music_seed,
            self.selected_archetype.name,
            self.run_music_theme or self.theme.name,
            self.run_modifier.name,
            depth=self.current_depth,
        )

    def sync_music(self) -> None:
        self.audio_available = self.audio.sync_music(
            self.current_music_profile(), self.music_enabled
        )

    def play_sfx(self, name: str) -> None:
        self.audio_available = self.audio.play_sfx(name, self.audio_enabled)

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

    def item_decision_summary(self, item: Item) -> str:
        if item.slot == "story_relic":
            return "Story relic · collect it to clarify the guest's plea"
        if item.slot == "potion":
            missing = max(0, self.player.max_hp - self.player.hp)
            return f"Restores {item.heal} HP" + (
                f" · missing {missing}" if missing else " · save for later"
            )
        if item.slot == "mana_potion":
            missing = max(0, int(self.player.max_mana - self.player.mana))
            return f"Restores {item.mana} mana" + (
                f" · missing {missing}" if missing else " · save for later"
            )
        if item.slot == "identify":
            unidentified = sum(
                1 for entry in self.player.inventory if entry.unidentified
            )
            return "Reveals best unknown item" + (
                f" · {unidentified} unknown" if unidentified else " · none unknown"
            )
        if item.unidentified:
            return "Unknown stats · use to reveal or identify safely"
        if item.slot in ("weapon", "armor"):
            equipped = self.player.equipment.get(item.slot)
            current = 0
            incoming = item.power if item.slot == "weapon" else item.defense
            if equipped:
                current = equipped.power if item.slot == "weapon" else equipped.defense
            delta = incoming - current
            stat = "damage" if item.slot == "weapon" else "armor"
            tradeoff = " · cursed power" if item.cursed else ""
            sign = "+" if delta > 0 else ""
            return f"{sign}{delta} {stat} vs equipped{tradeoff}"
        return "Use from inventory"

    def current_interaction_hint(self) -> tuple[str, str, str, Color] | None:
        if self.story_intro_pending:
            return (
                "1-3",
                "Guest dialog awaits",
                "Choose a story path to place the guest relic and begin the level.",
                self.story_state.accent if self.story_state else self.theme.accent,
            )
        story_relic = self.nearby_story_relic()
        if story_relic is not None:
            return (
                "E",
                f"Recover {story_relic.display_name}",
                self.item_decision_summary(story_relic),
                self.story_state.accent if self.story_state else self.theme.accent,
            )
        if self.player_near_stairs():
            if self.current_depth < DUNGEON_DEPTH:
                return (
                    "E",
                    f"Descend to depth {self.current_depth + 1}/{DUNGEON_DEPTH}",
                    "Stairs are safe only when you choose to leave.",
                    self.theme.stair,
                )
            if self.boss_alive():
                return (
                    "!",
                    "Gate sealed",
                    "Defeat the gate tyrant before using the final stairs.",
                    (245, 95, 70),
                )
            return (
                "E",
                "Complete the run",
                "The tyrant is dead; descend to claim victory.",
                self.theme.stair,
            )
        guest = self.nearby_story_guest()
        if guest:
            return (
                "1-3",
                f"{guest.name}, {guest.role}",
                self.story_choices_hint(guest),
                guest.color,
            )
        secret = self.nearby_secret()
        if secret:
            hint = SECRET_HINTS.get(
                secret.kind,
                InteractionHint(
                    secret.kind, "Open the revealed secret.", self.theme.accent
                ),
            )
            return ("E", hint.title, hint.detail, hint.color)
        shrine = self.nearby_shrine()
        if shrine:
            hint = SHRINE_HINTS.get(
                shrine.kind,
                InteractionHint(
                    shrine.kind, "Use the shrine's bargain.", self.theme.accent
                ),
            )
            return ("E", hint.title, hint.detail, hint.color)
        item = self.nearby_item()
        if item:
            return (
                "E",
                f"Pick up {item.display_name}",
                self.item_decision_summary(item),
                self.rarity_color(item.visible_rarity),
            )
        trap = self.nearby_trap_warning()
        if trap:
            hint = TRAP_HINTS.get(
                trap.kind,
                InteractionHint(
                    trap.kind, "Dangerous floor trigger nearby.", (245, 95, 70)
                ),
            )
            return ("!", hint.title, hint.detail, hint.color)
        return None

    def save_exists(self) -> bool:
        return self.save_path.exists()

    def theme_by_name(self, name: str) -> Any:
        return next(
            (theme for theme in DUNGEON_THEMES if theme.name == name), self.theme
        )

    def start_story_mode(self) -> None:
        self.story_seed = self.rng.randrange(1, 2**31)
        self.story_state = StoryEngine.generate(
            self.story_seed,
            self.selected_archetype.name,
            self.run_number,
            self.theme.name,
            self.run_modifier.name,
        )
        self.story_guests = []
        self._apply_story_theme_for_current_depth()

    def current_story_beat(self) -> Any:
        return story_beat_for_depth(self.story_state, self.current_depth)

    def story_effect_value(
        self, key: str, minimum: float = -1.0, maximum: float = 1.0
    ) -> float:
        return clamp_story_effect(story_effect(self.story_state, key), minimum, maximum)

    def story_header_line(self) -> str:
        if self.story_state is None:
            return "Story: unwritten"
        beat = self.current_story_beat()
        if beat is None:
            return f"Story: {self.story_state.title}"
        status = "resolved" if beat.resolved_choice else "unresolved"
        return f"Story: {self.story_state.title} · {beat.title} ({status})"

    def story_choice_preview(self, choice_key: str) -> str:
        previews = {
            "aid": "mercy wards, heals, and reveals",
            "bargain": "relic power for blood and curses",
            "defy": "damage, XP, and hunters",
        }
        return previews.get(choice_key, "the dungeon answers")

    def story_choices_hint(self, guest: StoryGuest) -> str:
        entries = [
            f"{index + 1} {choice.label}: {self.story_choice_preview(choice.key)}"
            for index, choice in enumerate(guest.choices[:3])
        ]
        return " · ".join(entries) + " · E hear plea"

    def quest_cutscene_context(self, guest: StoryGuest | None = None) -> dict[str, str]:
        beat = self.current_story_beat()
        story = self.story_state
        active_guest = guest or self.current_story_guest_for_depth()
        if active_guest is None:
            active_guest = self.nearby_story_guest()
        motif = next(
            (
                candidate
                for candidate in STORY_LOCATION_MOTIFS
                if beat is not None and candidate.theme_name == beat.theme_name
            ),
            None,
        )
        location_image = (
            motif.image
            if motif is not None
            else (beat.theme_name.lower() if beat is not None else "unlit stone")
        )
        location_danger = (
            motif.danger if motif is not None else "the dungeon listens for hesitation"
        )
        guest_name = active_guest.name if active_guest else "Unknown Guest"
        guest_role = active_guest.role if active_guest else "Guest"
        guest_motive = active_guest.motive if active_guest else "waits for a choice"
        guest_dialogue = (
            active_guest.dialogue
            if active_guest
            else (beat.dialogue if beat else "The guest waits for an answer.")
        )
        cinematic_narration = "The dungeon waits in silence."
        if story is not None and beat is not None:
            cinematic_narration = (
                f"The narrator's candle reveals {location_image}. "
                f"Here, {location_danger}. {beat.summary} "
                f"{guest_name}, {guest_role}, {guest_motive}. "
                f"The relic glimmers as {story.relic_form}; {story.relic_temptation}. "
                f"{guest_dialogue}"
            )
        context = {
            "depth": str(self.current_depth),
            "player_class": getattr(
                self.player, "class_name", self.selected_archetype.name
            ),
            "story_title": story.title if story else "Unwritten Descent",
            "player_backstory": story.player_backstory
            if story
            else "An unnamed exile descends.",
            "objective": story.objective if story else "Survive the dungeon.",
            "antagonist": story.antagonist if story else "Gate Tyrant",
            "faction": story.faction if story else "the dungeon",
            "rival_faction": story.rival_faction if story else "the rival faction",
            "relic_name": story.relic_name if story else "Nameless Relic",
            "relic_form": story.relic_form if story else "a relic",
            "relic_temptation": story.relic_temptation
            if story
            else "it wants to be used",
            "location_image": location_image,
            "location_danger": location_danger,
            "cinematic_narration": cinematic_narration,
            "beat_title": beat.title if beat else "Unwritten Beat",
            "beat_summary": beat.summary if beat else "The floor waits in silence.",
            "beat_dialogue": beat.dialogue
            if beat
            else "The guest waits for an answer.",
            "guest_name": guest_name,
            "guest_role": guest_role,
            "guest_motive": guest_motive,
            "guest_dialogue": guest_dialogue,
        }
        return {key: " ".join(str(value).split()) for key, value in context.items()}

    def start_quest_cutscene(
        self, asset_id: str, guest: StoryGuest | None = None
    ) -> bool:
        asset = self.quest_cutscenes.get(asset_id)
        if asset is None:
            return False
        active_guest = guest or self.current_story_guest_for_depth()
        self.active_cutscene = ActiveQuestCutscene(
            asset_id=asset.id,
            node_id=asset.start_node,
            guest_depth=active_guest.depth if active_guest else self.current_depth,
            guest_beat_index=active_guest.beat_index if active_guest else -1,
            context=self.quest_cutscene_context(active_guest),
        )
        return True

    def close_active_cutscene(self) -> None:
        self.active_cutscene = None

    def active_cutscene_asset(self) -> Any:
        if self.active_cutscene is None:
            return None
        return self.quest_cutscenes.get(self.active_cutscene.asset_id)

    def active_cutscene_node(self) -> Any:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None:
            return None
        return asset.nodes.get(self.active_cutscene.node_id)

    def active_cutscene_guest(self) -> StoryGuest | None:
        if self.active_cutscene is None:
            return None
        if self.active_cutscene.guest_beat_index >= 0:
            for guest in self.story_guests:
                if (
                    guest.depth == self.active_cutscene.guest_depth
                    and guest.beat_index == self.active_cutscene.guest_beat_index
                ):
                    return guest
        return self.nearby_story_guest() or self.current_story_guest_for_depth()

    def active_cutscene_text(self) -> str:
        node = self.active_cutscene_node()
        if node is None or self.active_cutscene is None:
            return ""
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(node.text, context)

    def cutscene_narration_char_delay(self, char: str) -> float:
        if char == "\n":
            return 0.18
        if char in ".!?":
            return 0.25
        if char in ";:":
            return 0.16
        if char in ",—":
            return 0.10
        if char.isspace():
            return 0.012
        return 0.026

    def active_cutscene_narration_duration(self, text: str | None = None) -> float:
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0.0
        return sum(self.cutscene_narration_char_delay(char) for char in narration)

    def active_cutscene_narration_char_count(self, text: str | None = None) -> int:
        if self.active_cutscene is None:
            return 0
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0
        elapsed = max(0.0, self.active_cutscene.node_elapsed)
        spoken_time = 0.0
        for index, char in enumerate(narration):
            spoken_time += self.cutscene_narration_char_delay(char)
            if spoken_time > elapsed:
                return index
        return len(narration)

    def active_cutscene_visible_text(self) -> str:
        narration = self.active_cutscene_text()
        return narration[: self.active_cutscene_narration_char_count(narration)]

    def active_cutscene_narration_complete(self) -> bool:
        narration = self.active_cutscene_text()
        return self.active_cutscene_narration_char_count(narration) >= len(narration)

    def active_cutscene_narration_progress(self) -> float:
        narration = self.active_cutscene_text()
        if not narration:
            return 1.0
        return min(
            1.0, self.active_cutscene_narration_char_count(narration) / len(narration)
        )

    def active_cutscene_current_sentence_text(self) -> str:
        narration = self.active_cutscene_text()
        if not narration:
            return ""
        char_count = self.active_cutscene_narration_char_count(narration)
        if char_count <= 0:
            return ""
        cursor = min(char_count, len(narration))
        start = 0
        for mark in (". ", "! ", "? ", "\n"):
            found = narration.rfind(mark, 0, cursor)
            if found >= 0:
                start = max(start, found + len(mark))
        end_candidates = [
            found
            for mark in (".", "!", "?", "\n")
            if (found := narration.find(mark, cursor)) >= 0
        ]
        end = min(end_candidates) if end_candidates else len(narration)
        return narration[start:end].strip()

    def reveal_active_cutscene_narration(self) -> None:
        if self.active_cutscene is None:
            return
        self.active_cutscene.node_elapsed = max(
            self.active_cutscene.node_elapsed,
            self.active_cutscene_narration_duration() + 0.05,
        )

    def active_cutscene_speaker_name(self) -> str:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None or self.active_cutscene is None:
            return "Narrator"
        if node.speaker == "narrator":
            return "Narrator"
        actor = asset.actors.get(node.speaker)
        if actor is None:
            return node.speaker.title()
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(actor.name, context)

    def active_cutscene_choices(self) -> list[RuntimeDialogueChoice]:
        node = self.active_cutscene_node()
        if node is None:
            return []
        if node.choice_source == "story_relic_options":
            return [
                RuntimeDialogueChoice(
                    label=label,
                    detail=detail,
                    action="choose_story_relic_path",
                    choice_key=choice_key,
                    source_index=index,
                )
                for index, (choice_key, label, detail) in enumerate(
                    self.story_relic_choice_options()
                )
            ]
        if node.choice_source == "story_guest_choices":
            guest = self.active_cutscene_guest()
            if guest is None:
                return []
            return [
                RuntimeDialogueChoice(
                    label=choice.label,
                    detail=f"{choice.intent} ({self.story_choice_preview(choice.key)})",
                    action="resolve_story_choice",
                    choice_key=choice.key,
                    source_index=index,
                )
                for index, choice in enumerate(guest.choices[:3])
            ]
        context = (
            {**self.active_cutscene.context}
            if self.active_cutscene is not None
            else self.quest_cutscene_context()
        )
        return [
            RuntimeDialogueChoice(
                label=format_asset_text(choice.label, context),
                detail=format_asset_text(choice.detail, context),
                next_node=choice.next_node,
                action=choice.action,
                choice_key=choice.choice_key,
                source_index=index,
            )
            for index, choice in enumerate(node.choices)
        ]

    def set_active_cutscene_node(self, node_id: str) -> bool:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None or node_id not in asset.nodes:
            return False
        self.active_cutscene.node_id = node_id
        self.active_cutscene.node_elapsed = 0.0
        self.active_cutscene.context = self.quest_cutscene_context(
            self.active_cutscene_guest()
        )
        return True

    def advance_active_cutscene(self) -> bool:
        if self.active_cutscene is None:
            return False
        if not self.active_cutscene_narration_complete():
            self.reveal_active_cutscene_narration()
            return True
        choices = self.active_cutscene_choices()
        if len(choices) == 1 and choices[0].next_node and not choices[0].action:
            return self.set_active_cutscene_node(choices[0].next_node)
        if not choices:
            self.close_active_cutscene()
            return True
        return False

    def choose_active_cutscene_option(self, choice_index: int) -> bool:
        if self.active_cutscene is None:
            return False
        choices = self.active_cutscene_choices()
        if not (0 <= choice_index < len(choices)):
            return False
        choice = choices[choice_index]
        if choice.action == "choose_story_relic_path":
            return self.choose_story_relic_path(choice.source_index)
        if choice.action == "resolve_story_choice":
            guest = self.active_cutscene_guest()
            if guest is None:
                return False
            resolved = self.resolve_story_choice(guest, choice.source_index)
            if resolved:
                self.close_active_cutscene()
            return resolved
        if choice.action == "close":
            self.close_active_cutscene()
            return True
        if choice.next_node:
            return self.set_active_cutscene_node(choice.next_node)
        self.close_active_cutscene()
        return True

    def update_active_cutscene(self, dt: float) -> None:
        if self.active_cutscene is None:
            return
        self.active_cutscene.elapsed += dt
        self.active_cutscene.node_elapsed += dt

    def story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        beat = self.current_story_beat()
        if self.story_state is None or beat is None:
            return self.default_story_relic_choice_options()
        base_seed = self.story_relic_choice_text_seed(beat)
        key_salts = {"aid": 11_117, "bargain": 65_537, "defy": 104_729}
        return [
            self.story_relic_choice_option_for_key(
                key, beat, random.Random(base_seed + key_salts[key])
            )
            for key in self.story_relic_choice_key_order(beat)
        ]

    def story_relic_choice_key_order(self, beat: Any) -> list[str]:
        keys = ["aid", "bargain", "defy"]
        rng = random.Random(self.story_relic_choice_text_seed(beat) ^ 0xA511E9B3)
        rng.shuffle(keys)
        if keys == ["aid", "bargain", "defy"]:
            keys = ["bargain", "defy", "aid"]
        return keys

    def default_story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        return [
            (
                "aid",
                "Offer a gentle vow",
                "promise to carry the guest's burden before your own",
            ),
            (
                "bargain",
                "Whisper a hidden bargain",
                "ask the dungeon to answer in riddles, debts, and signs",
            ),
            (
                "defy",
                "Refuse the omen",
                "turn from the guest's terms and trust your own path",
            ),
        ]

    def story_relic_choice_text_seed(self, beat: Any) -> int:
        parts = [
            str(self.story_seed),
            str(self.run_number),
            str(self.current_depth),
            beat.title,
            beat.guest_name,
            beat.guest_role,
        ]
        if self.story_state is not None:
            parts.extend(
                (
                    self.story_state.title,
                    self.story_state.faction,
                    self.story_state.rival_faction,
                    self.story_state.relic_name,
                )
            )
        seed = 2_166_136_261
        for char in "|".join(parts):
            seed ^= ord(char)
            seed = (seed * 16_777_619) & 0xFFFFFFFF
        return seed

    def story_relic_choice_option_for_key(
        self, choice_key: str, beat: Any, rng: random.Random
    ) -> tuple[str, str, str]:
        choice = next(
            (candidate for candidate in beat.choices if candidate.key == choice_key),
            None,
        )
        if choice is None:
            return next(
                option
                for option in self.default_story_relic_choice_options()
                if option[0] == choice_key
            )
        guest = self.story_choice_short_name(beat.guest_name)
        role = self.safe_story_choice_text(beat.guest_role.lower(), "guest")
        relic = self.safe_story_choice_text(
            self.story_state.relic_name
            if self.story_state is not None
            else "the relic",
            "the relic",
        )
        faction = self.safe_story_choice_text(
            self.story_state.faction if self.story_state is not None else "the dungeon",
            "the dungeon",
        )
        antagonist = self.safe_story_choice_text(
            self.story_state.antagonist
            if self.story_state is not None
            else "the tyrant",
            "the tyrant",
        )
        motive = self.short_story_choice_clause(beat.guest_motive, 36)
        title = self.safe_story_choice_text(beat.title, "this omen")
        intent = self.short_story_choice_clause(choice.intent, 48)
        label_templates = {
            "aid": (
                "Keep {guest}'s vow",
                "Mercy for the {role}",
                "Answer {guest} kindly",
                "Carry {guest}'s plea",
                "Honor the {role}",
            ),
            "bargain": (
                "Name {guest}'s price",
                "Trade a sealed vow",
                "Speak in owed terms",
                "Bind {relic}'s debt",
                "Ask the {role}'s price",
            ),
            "defy": (
                "Refuse {guest}'s terms",
                "Break the old demand",
                "Challenge {antagonist}'s claim",
                "Trust your own oath",
                "Deny the {role}'s omen",
            ),
        }
        detail_templates = {
            "aid": (
                "{intent}; remember {motive}",
                "answer {guest} as {role}: {intent}",
                "set {relic} toward mercy: {intent}",
                "let {title} end in witness: {intent}",
            ),
            "bargain": (
                "{intent}; weigh it against {faction}",
                "answer {guest} with measured terms: {intent}",
                "bind {relic} to a price: {intent}",
                "let {title} become debt: {intent}",
            ),
            "defy": (
                "{intent}; keep {relic} in your own hands",
                "answer {guest} with iron restraint: {intent}",
                "set your oath against {antagonist}: {intent}",
                "let {title} break before you: {intent}",
            ),
        }
        format_values = {
            "guest": guest,
            "role": role,
            "relic": relic,
            "faction": faction,
            "antagonist": antagonist,
            "motive": motive,
            "title": title,
            "intent": intent,
        }
        label = rng.choice(label_templates[choice_key]).format(**format_values)
        detail = rng.choice(detail_templates[choice_key]).format(**format_values)
        return (
            choice_key,
            self.short_story_choice_clause(label, 34),
            self.short_story_choice_clause(detail, 92),
        )

    def story_choice_short_name(self, name: str) -> str:
        safe_name = self.safe_story_choice_text(name, "the guest")
        parts = safe_name.split()
        if len(parts) > 2:
            safe_name = " ".join(parts[:2])
        return safe_name

    def safe_story_choice_text(self, text: str, fallback: str) -> str:
        result = " ".join(str(text).replace("\n", " ").split())
        replacements = {
            "unguarded": "alone",
            "guarded": "watched",
            "guardian": "warden",
            "guidance": "counsel",
            "guiding": "veiled",
            "guide": "shape",
            "light": "sign",
            "beacon": "sign",
            "lantern": "taper",
            "trail": "trace",
        }
        for term, replacement in replacements.items():
            result = re.sub(term, replacement, result, flags=re.IGNORECASE)
        result = " ".join(result.split()).strip(" ;:,.—")
        return result or fallback

    def short_story_choice_clause(self, text: str, limit: int) -> str:
        safe = self.safe_story_choice_text(text, "the guest's plea")
        if len(safe) <= limit:
            return safe
        shortened = safe[: max(1, limit - 1)].rsplit(" ", 1)[0].strip(" ;:,.—")
        return f"{shortened}…" if shortened else safe[:limit]

    def story_relic_choice_traits(self, choice_key: str) -> tuple[bool, bool]:
        traits = {
            "aid": (True, False),
            "bargain": (True, True),
            "defy": (False, True),
        }
        return traits.get(choice_key, (True, False))

    def story_relic_choice_label(self) -> str:
        for key, label, _detail in self.story_relic_choice_options():
            if key == self.story_relic_choice_key:
                return label
        return "unbound"

    def current_story_guest_for_depth(self) -> StoryGuest | None:
        return next(
            (
                guest
                for guest in self.story_guests
                if guest.depth == self.current_depth and not guest.resolved
            ),
            None,
        )

    def current_story_relic(self) -> Item | None:
        return next((item for item in self.items if item.slot == "story_relic"), None)

    def story_relic_target_position(self) -> tuple[float, float] | None:
        relic = self.current_story_relic()
        if relic is not None:
            return relic.x, relic.y
        if not self.story_relic_collected:
            return self.story_relic_position
        return None

    def begin_story_level_intro(self) -> None:
        beat = self.current_story_beat()
        guest = self.current_story_guest_for_depth()
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = ""
        self.story_relic_position = None
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = False
        self.story_relic_guarded = False
        self.items = [item for item in self.items if item.slot != "story_relic"]
        self.story_intro_pending = beat is not None and guest is not None
        if self.story_intro_pending:
            self.start_quest_cutscene("story_guest_omen", guest)
        else:
            self.close_active_cutscene()

    def story_intro_lines(self) -> list[str]:
        if self.story_state is None:
            return []
        beat = self.current_story_beat()
        guest = self.current_story_guest_for_depth()
        lines = [self.story_state.title, self.story_state.objective]
        if beat is not None:
            lines.extend(
                [
                    f"Depth {beat.depth}: {beat.title}",
                    beat.summary,
                    beat.dialogue,
                ]
            )
        if guest is not None:
            lines.append(
                f"{guest.name}, {guest.role}, waits somewhere ahead. Before the level begins, choose how their relic echo should surface."
            )
            lines.append(
                "Your answer will shape how the relic stirs, but the dungeon will not reveal the cost until the level begins."
            )
        return lines

    def choose_story_relic_path(self, choice_index: int) -> bool:
        options = self.story_relic_choice_options()
        if not self.story_intro_pending or not (0 <= choice_index < len(options)):
            return False
        choice_key, choice_label, _detail = options[choice_index]
        guidance_enabled, guarded = self.story_relic_choice_traits(choice_key)
        guest = self.current_story_guest_for_depth()
        if guest is None:
            self.story_intro_pending = False
            return False
        relic_x, relic_y = self.story_relic_location_for_choice(choice_key, guest)
        self.items = [item for item in self.items if item.slot != "story_relic"]
        relic_name = (
            f"{guest.name}'s Echo of {self.story_state.relic_name}"
            if self.story_state is not None
            else "Guest Relic Echo"
        )
        self.items.append(
            Item(
                relic_name,
                "story_relic",
                rarity="Unique",
                x=relic_x,
                y=relic_y,
                affixes=[
                    "Story Relic",
                    choice_label,
                    "Guiding Light" if guidance_enabled else "No Guiding Light",
                    "Guarded" if guarded else "Unguarded",
                ],
                unique_effect="guides the guest's plea"
                if guidance_enabled
                else "the guest's light has gone silent",
            )
        )
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = choice_key
        self.story_relic_position = (relic_x, relic_y)
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = guidance_enabled
        self.story_relic_guarded = guarded
        if guarded:
            self.spawn_story_relic_guard(relic_x, relic_y)
        self.story_intro_pending = False
        self.close_active_cutscene()
        if self.story_state is not None:
            self.story_state.flags.append(f"{self.current_depth}:relic:{choice_key}")
            self.story_state.log.append(
                f"Depth {self.current_depth}: {choice_label} — the guest relic surfaced"
                f" {'with a guiding light' if guidance_enabled else 'without a guiding light'}"
                f" {'and a guardian' if guarded else 'and no guardian'}."
            )
            del self.story_state.log[:-12]
        self.floaters.append(
            FloatingText(
                f"{choice_label}: "
                f"{'follow the relic trail' if guidance_enabled else 'find the relic without a trail'}",
                self.player.x,
                self.player.y - 0.6,
                self.story_state.accent if self.story_state else self.theme.accent,
                ttl=1.8,
            )
        )
        self.play_sfx("shrine")
        self.save_run()
        return True

    def story_relic_location_for_choice(
        self, choice_key: str, guest: StoryGuest
    ) -> tuple[float, float]:
        if choice_key == "aid":
            return self.drop_position_near(guest.x, guest.y)
        if choice_key == "bargain":
            if self.secrets:
                secret = min(
                    self.secrets,
                    key=lambda candidate: math.hypot(
                        candidate.x - guest.x, candidate.y - guest.y
                    ),
                )
                secret.revealed = True
                return self.drop_position_near(secret.x, secret.y)
            side_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            room = max(
                side_rooms,
                key=lambda candidate: math.hypot(
                    candidate.center[0] + 0.5 - self.player.x,
                    candidate.center[1] + 0.5 - self.player.y,
                ),
            )
            x, y = room.random_point(self.rng)
            return self.drop_position_near(x, y)
        final_room = self.dungeon.rooms[-1]
        x, y = final_room.random_point(self.rng)
        return self.drop_position_near(x, y)

    def spawn_story_relic_guard(self, relic_x: float, relic_y: float) -> None:
        offsets = (
            (1.8, 0.0),
            (-1.8, 0.0),
            (0.0, 1.8),
            (0.0, -1.8),
            (1.4, 1.4),
            (-1.4, 1.4),
            (1.4, -1.4),
            (-1.4, -1.4),
        )
        guard_x, guard_y = relic_x, relic_y
        for ox, oy in offsets:
            candidate_x, candidate_y = relic_x + ox, relic_y + oy
            if not self.dungeon.blocked_for_radius(
                candidate_x, candidate_y, radius=0.28
            ):
                guard_x, guard_y = candidate_x, candidate_y
                break
        guard = self._make_story_hunter(guard_x, guard_y, prefix="Relic Guardian")
        guard.kind = "miniboss"
        guard.name = f"Relic Guardian {guard.name.split(' ', 2)[-1]}"
        guard.elite_modifier = "Relic Guardian"
        guard.telegraph = "bound to the guest relic by the opening story choice"
        guard.max_hp = max(1, int(guard.max_hp * 1.45))
        guard.hp = guard.max_hp
        guard.damage += 3 + self.current_depth // 2
        guard.xp += 24 + self.current_depth * 2
        guard.aggro_range += 3.0
        guard.color = self.story_state.accent if self.story_state else self.theme.accent
        self.enemies.append(guard)

    def story_mechanics_summary(self) -> str:
        if self.story_state is None:
            return ""
        forces: list[str] = []
        resist = self.story_effect_value("damage_resist", 0.0, 0.35)
        if resist > 0:
            forces.append(f"Mercy ward -{int(round(resist * 100))}% damage")
        healing = self.story_effect_value("healing_echo", 0.0, 1.0)
        if healing > 0:
            forces.append(f"Echo heals {int(round(min(1.0, healing) * 100))}% on kills")
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic > 0:
            forces.append(f"Relic power +{int(round(relic * 100))}% spell force")
        blood = self.story_effect_value("blood_price", 0.0, 0.35)
        if blood > 0:
            forces.append("Blood price drains HP on spells")
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        if damage > 0:
            forces.append(f"Defiance +{int(round(damage * 100))}% damage")
        hunters = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        if hunters > 0:
            forces.append("Hunters stalk each new floor")
        pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        if abs(pressure) >= 0.01:
            direction = "more" if pressure > 0 else "fewer"
            forces.append(f"{direction} enemies {int(round(abs(pressure) * 100))}%")
        loot = self.story_effect_value("loot_bonus", 0.0, 0.35)
        if loot > 0:
            forces.append(f"loot +{int(round(loot * 100))}%")
        traps = self.story_effect_value("trap_bonus", 0.0, 0.28)
        if traps > 0:
            forces.append(f"traps +{int(round(traps * 100))}%")
        return " · ".join(forces[:7])

    def story_panel_lines(self) -> list[str]:
        if self.story_state is None:
            return []
        lines = [
            self.story_state.title,
            f"Goal: {self.story_state.objective}",
        ]
        beat = self.current_story_beat()
        if beat is not None:
            status = beat.resolved_choice or "awaiting choice"
            lines.append(f"Depth {beat.depth}: {beat.title} — {status}")
            lines.append(beat.summary)
            if beat.outcome:
                lines.append(f"Outcome: {beat.outcome}")
            else:
                lines.append(beat.dialogue)
                guest = self.nearby_story_guest()
                if guest is not None:
                    choice_details = [
                        f"{index + 1} {choice.label}: {choice.intent} ({self.story_choice_preview(choice.key)})"
                        for index, choice in enumerate(guest.choices[:3])
                    ]
                    lines.append("Choices: " + " · ".join(choice_details))
        mechanics = self.story_mechanics_summary()
        if self.story_intro_pending:
            lines.append(
                "Guest relic: choose 1-3 to bind its first location before the level begins."
            )
        elif self.story_relic_choice_key and not self.story_relic_collected:
            cues = (
                "follow the guiding light"
                if self.story_relic_guidance_enabled
                else "no guiding light; search from the choice clue"
            )
            guard = (
                "guarded by a relic guardian"
                if self.story_relic_guarded
                else "unguarded"
            )
            lines.append(
                f"Guest relic: {self.story_relic_choice_label()} — {cues}; {guard}."
            )
        elif self.story_relic_collected:
            lines.append("Guest relic: recovered; the guest's plea is clearer.")
        if mechanics:
            lines.append(f"Story forces: {mechanics}")
        elif self.story_state.log:
            lines.append(self.story_state.log[-1])
        return lines

    def story_player_damage_bonus(self, spell: bool = False) -> float:
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        relic_weight = 1.0 if spell else 0.6
        return min(0.55, damage + relic * relic_weight)

    def apply_story_player_damage(self, damage: int, spell: bool = False) -> int:
        bonus = self.story_player_damage_bonus(spell=spell)
        if bonus <= 0:
            return max(1, damage)
        return max(1, int(round(damage * (1.0 + bonus))))

    def apply_story_blood_price(self, reason: str) -> int:
        price = self.story_effect_value("blood_price", 0.0, 0.35)
        if price <= 0 or self.player.hp <= 1:
            return 0
        cost = max(
            1,
            min(10, int(round(self.player.max_hp * (0.015 + price * 0.18)))),
        )
        actual = min(cost, self.player.hp - 1)
        if actual <= 0:
            return 0
        self.player.hp -= actual
        self.run_stats.damage_taken += actual
        self.floaters.append(
            FloatingText(
                f"{reason.title()} blood price -{actual}",
                self.player.x,
                self.player.y - 0.55,
                self.story_state.accent if self.story_state else (190, 60, 85),
                ttl=1.0,
            )
        )
        self.add_impact(
            self.player.x,
            self.player.y,
            self.story_state.accent if self.story_state else (190, 60, 85),
            ttl=0.36,
            radius=0.42,
            kind="blood",
        )
        return actual

    def resolve_unanswered_story_beat(self) -> str:
        if self.story_state is None:
            return ""
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        beat = self.current_story_beat()
        if beat is None or beat_index is None or beat.resolved_choice:
            return ""
        if not record_unanswered_story_beat(self.story_state, self.current_depth):
            return ""
        for guest in self.story_guests:
            if guest.depth == self.current_depth and guest.beat_index == beat_index:
                guest.resolved = True
                guest.resolved_choice = "unanswered"
        return f"{beat.guest_name} was forsaken; hunters stir below"

    def _apply_story_theme_for_current_depth(self) -> None:
        beat = self.current_story_beat()
        if beat is not None:
            self.theme = self.theme_by_name(beat.theme_name)
            self.run_music_theme = self.theme.name

    def _populate_story_guest(self) -> None:
        if self.story_state is None:
            return
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        if beat_index is None:
            return
        beat = self.story_state.beats[beat_index]
        if beat.resolved_choice:
            return
        if any(
            guest.depth == self.current_depth and guest.beat_index == beat_index
            for guest in self.story_guests
        ):
            return
        available_rooms = self.dungeon.rooms[1:-1] or self.dungeon.rooms[:1]
        if not available_rooms:
            return
        room = available_rooms[(self.current_depth + beat_index) % len(available_rooms)]
        x, y = room.random_point(self.rng)
        self.story_guests.append(
            story_guest_from_beat(self.story_state, beat_index, x, y)
        )

    def nearby_story_guest(self) -> StoryGuest | None:
        nearby = [
            guest
            for guest in self.story_guests
            if not guest.resolved
            and guest.depth == self.current_depth
            and math.hypot(guest.x - self.player.x, guest.y - self.player.y) < 1.25
        ]
        return min(
            nearby,
            key=lambda guest: math.hypot(
                guest.x - self.player.x, guest.y - self.player.y
            ),
            default=None,
        )

    def mark_story_guest_met(self, guest: StoryGuest) -> None:
        if not guest.met:
            guest.met = True
            self.run_stats.guests_met += 1

    def talk_to_story_guest(self, guest: StoryGuest) -> None:
        self.mark_story_guest_met(guest)
        if self.start_quest_cutscene("story_guest_dialogue", guest):
            return
        self.floaters.append(
            FloatingText(
                f"{guest.role}: choose 1-3",
                guest.x,
                guest.y - 0.55,
                guest.color,
                ttl=1.4,
            )
        )
        self.floaters.append(
            FloatingText(
                guest.motive[:42],
                guest.x,
                guest.y - 0.2,
                (225, 215, 190),
                ttl=1.4,
            )
        )

    def resolve_story_choice(self, guest: StoryGuest, choice_index: int) -> bool:
        if guest.resolved or not (0 <= choice_index < len(guest.choices)):
            return False
        choice = guest.choices[choice_index]
        self.mark_story_guest_met(guest)
        guest.resolved = True
        guest.resolved_choice = choice.key
        if self.story_state is not None:
            record_story_choice(self.story_state, guest.depth, choice)
        self.run_stats.story_choices += 1
        self._apply_story_choice_reward(guest, choice.key)
        self.floaters.append(
            FloatingText(
                f"{choice.label}: story changed",
                guest.x,
                guest.y - 0.65,
                guest.color,
                ttl=1.5,
            )
        )
        self.add_impact(
            guest.x, guest.y, guest.color, ttl=0.58, radius=0.7, kind="burst"
        )
        if (
            self.active_cutscene is not None
            and self.active_cutscene.guest_depth == guest.depth
            and self.active_cutscene.guest_beat_index == guest.beat_index
        ):
            self.close_active_cutscene()
        self.play_sfx("shrine")
        self.save_run()
        return True

    def _apply_story_choice_reward(self, guest: StoryGuest, choice_key: str) -> None:
        if choice_key == "aid":
            self.player.hp = min(
                self.player.max_hp, self.player.hp + max(16, self.player.max_hp // 5)
            )
            self.player.mana = min(
                self.player.max_mana,
                self.player.mana + max(10, self.player.max_mana // 4),
            )
            self.player.stamina = self.player.max_stamina
            revealed = 0
            for secret in sorted(
                self.secrets,
                key=lambda secret: math.hypot(secret.x - guest.x, secret.y - guest.y),
            ):
                if secret.opened or secret.revealed:
                    continue
                if math.hypot(secret.x - guest.x, secret.y - guest.y) > 7.0:
                    continue
                secret.revealed = True
                revealed += 1
                if revealed >= 2:
                    break
            if revealed == 0:
                cache_x, cache_y = self.drop_position_near(guest.x, guest.y)
                self.secrets.append(
                    SecretCache(cache_x, cache_y, "Mercy-Sealed Cache", revealed=True)
                )
            self.shrines.append(Shrine(guest.x, guest.y, "Mending Shrine"))
        elif choice_key == "bargain":
            blood_price = self.story_effect_value("blood_price", 0.0, 0.35)
            cost = max(
                6,
                min(22, int(round(self.player.max_hp * (0.08 + blood_price * 0.45)))),
            )
            previous_hp = self.player.hp
            self.player.hp = max(1, self.player.hp - cost)
            self.run_stats.damage_taken += previous_hp - self.player.hp
            item = self._make_equipment(
                self.rng.choice(("weapon", "armor")),
                "Rare",
                guest.x,
                guest.y,
            )
            self._empower_story_relic_item(item, guaranteed=True)
            self.items.append(item)
        elif choice_key == "defy":
            leveled = self.player.gain_xp(24 + self.current_depth * 3)
            if leveled:
                self.grant_skill_upgrade(reason="story defiance")
            spawn_x, spawn_y = self.drop_position_near(guest.x, guest.y)
            self.enemies.append(
                self._make_story_hunter(spawn_x, spawn_y, prefix="Story-Marked")
            )

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
        self.start_story_mode()
        self.tile_cache.clear()
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
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
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
            self.state = "victory"
            self.unlock_hell_difficulty()
            self.audio.stop_music()
            self.play_sfx("victory")
            self.delete_save()
            return
        unanswered_message = self.resolve_unanswered_story_beat()
        self.current_depth += 1
        self.theme = self.rng.choice(DUNGEON_THEMES)
        self._apply_story_theme_for_current_depth()
        self.tile_cache.clear()
        self.dungeon = Dungeon(self.rng)
        start_x, start_y = self.dungeon.rooms[0].center
        self.player.x = start_x + 0.5
        self.player.y = start_y + 0.5
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

    def _populate_dungeon(self) -> None:
        final_room_index = len(self.dungeon.rooms) - 1
        difficulty = self.difficulty_profile()
        enemy_pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        loot_bonus = self.story_effect_value("loot_bonus", -0.2, 0.35)
        trap_bonus = self.story_effect_value("trap_bonus", -0.1, 0.28)
        shrine_bonus = self.story_effect_value("shrine_bonus", -0.1, 0.28)
        secret_bonus = self.story_effect_value("secret_bonus", -0.1, 0.28)
        hunter_pressure = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            is_final_room = room_index == final_room_index
            count = self.rng.randrange(1, 4)
            if self.current_depth <= 2:
                count = max(1, count - 1)
            elif self.current_depth >= 7:
                count += 1
            if enemy_pressure > 0 and self.rng.random() < enemy_pressure:
                count += 1
            elif enemy_pressure < 0 and self.rng.random() < abs(enemy_pressure):
                count = max(1, count - 1)
            if is_final_room:
                count += 1
            count = max(1, count + difficulty.enemy_count_bonus)
            if self.rng.random() < difficulty.enemy_extra_chance:
                count += 1
            for _ in range(count):
                self.enemies.append(
                    self._make_enemy(
                        *room.random_point(self.rng), final_room=is_final_room
                    )
                )

            if is_final_room and self.current_depth == DUNGEON_DEPTH:
                bx, by = room.center
                self.enemies.append(self._make_boss(bx + 0.5, by + 0.5))

            loot_chance = max(
                0.12,
                min(
                    0.88,
                    0.68
                    + self.run_modifier.loot_bonus
                    + loot_bonus
                    + difficulty.loot_chance_bonus,
                ),
            )
            if self.rng.random() < loot_chance:
                self.items.append(self._make_loot(*room.random_point(self.rng)))
            if (
                room_index > 3
                and not is_final_room
                and self.rng.random() < self.miniboss_chance()
            ):
                mx, my = room.random_point(self.rng)
                self.enemies.append(self._make_miniboss(mx, my))
            if room_index > 1 and self.rng.random() < max(
                0.04,
                min(
                    0.70,
                    0.24
                    + self.run_modifier.trap_bonus
                    + trap_bonus
                    + difficulty.trap_chance_bonus,
                ),
            ):
                tx, ty = room.random_point(self.rng)
                kind, min_damage, max_damage = self.rng.choice(TRAP_DEFINITIONS)
                depth_damage = max(0, self.current_depth - 3)
                raw_damage = (
                    self.rng.randrange(min_damage, max_damage + 1) + depth_damage
                )
                self.traps.append(
                    Trap(
                        tx,
                        ty,
                        kind,
                        max(
                            1,
                            int(round(raw_damage * difficulty.trap_damage_multiplier)),
                        ),
                    )
                )
            shrine_chance = (
                0.18
                + (0.08 if self.run_modifier.name == "Trap-Laced" else 0.0)
                + shrine_bonus
                + difficulty.shrine_chance_bonus
            )
            if room_index > 2 and self.rng.random() < max(
                0.04, min(0.46, shrine_chance)
            ):
                sx, sy = room.random_point(self.rng)
                self.shrines.append(Shrine(sx, sy, self.rng.choice(SHRINE_TYPES)))
            if (
                room_index > 2
                and not is_final_room
                and self.rng.random()
                < max(
                    0.03,
                    min(0.42, 0.16 + self.run_modifier.loot_bonus + secret_bonus),
                )
            ):
                cx, cy = room.random_point(self.rng)
                self.secrets.append(
                    SecretCache(
                        cx,
                        cy,
                        self.rng.choice(SECRET_TYPES),
                    )
                )

        if self.rng.random() < max(
            0.10,
            min(
                0.72,
                0.45
                + self.run_modifier.loot_bonus
                + secret_bonus
                + difficulty.loot_chance_bonus * 0.5,
            ),
        ):
            room = self.rng.choice(self.dungeon.rooms[2:-1])
            cx, cy = room.random_point(self.rng)
            self.secrets.append(SecretCache(cx, cy, "Lost Cartographer's Stash"))

        if hunter_pressure > 0 and len(self.dungeon.rooms) > 2:
            hunter_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            hunter_count = min(4, 1 + int(hunter_pressure / 0.14))
            if self.rng.random() < min(0.75, hunter_pressure * 1.5):
                hunter_count += 1
            for _ in range(hunter_count):
                room = self.rng.choice(hunter_rooms)
                hx, hy = room.random_point(self.rng)
                self.enemies.append(self._make_story_hunter(hx, hy))

        sx, sy = self.dungeon.rooms[0].random_point(self.rng)
        self.items.append(
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common", x=sx, y=sy)
        )
        self._populate_story_guest()

    def _apply_run_modifier(self, enemy: Enemy) -> Enemy:
        difficulty = self.difficulty_profile()
        depth_multiplier = 1.0 + max(0, self.current_depth - 1) * 0.045
        story_pressure = self.story_effect_value("enemy_pressure", -0.25, 0.35)
        story_multiplier = 1.0 + max(-0.12, min(0.22, story_pressure * 0.55))
        if enemy.kind == "boss":
            story_multiplier += self.story_effect_value("boss_pressure", 0.0, 0.35)
        enemy.max_hp = max(
            1,
            int(
                enemy.max_hp
                * self.run_modifier.enemy_hp_multiplier
                * depth_multiplier
                * story_multiplier
                * difficulty.enemy_hp_multiplier
            ),
        )
        enemy.hp = enemy.max_hp
        damage = enemy.damage + self.run_modifier.enemy_damage_bonus
        damage += max(0, self.current_depth - 4) // 2
        if story_pressure > 0:
            damage += int(story_pressure * 8)
        if enemy.kind == "boss":
            damage += int(self.story_effect_value("boss_pressure", 0.0, 0.35) * 10)
        enemy.damage = max(
            1,
            int(round(damage * difficulty.enemy_damage_multiplier))
            + difficulty.enemy_damage_bonus,
        )
        enemy.speed *= difficulty.enemy_speed_multiplier
        enemy.attack_cooldown = max(
            0.35,
            enemy.attack_cooldown * difficulty.enemy_attack_cooldown_multiplier,
        )
        enemy.aggro_range += (
            self.run_modifier.enemy_aggro_bonus
            + max(0.0, story_pressure)
            + difficulty.enemy_aggro_bonus
        )
        return enemy

    def _weighted_enemy_definition(self, final_room: bool = False) -> EnemyDefinition:
        definitions = FINAL_ROOM_ENEMY_DEFINITIONS if final_room else ENEMY_DEFINITIONS
        total_weight = sum(definition.weight for definition in definitions)
        roll = self.rng.randrange(total_weight)
        current = 0
        for definition in definitions:
            current += definition.weight
            if roll < current:
                return definition
        return definitions[-1]

    def _make_enemy(self, x: float, y: float, final_room: bool = False) -> Enemy:
        definition = self._weighted_enemy_definition(final_room)
        enemy = Enemy(
            definition.name,
            definition.kind,
            x,
            y,
            definition.max_hp,
            definition.max_hp,
            definition.speed,
            definition.damage,
            definition.xp,
            definition.attack_range,
            definition.attack_cooldown,
            aggro_range=definition.aggro_range,
            color=definition.color,
        )
        enemy = self._apply_run_modifier(enemy)
        if enemy.kind != "boss" and self.rng.random() < self.elite_chance():
            self._apply_elite_modifier(enemy)
        return enemy

    def elite_chance(self) -> float:
        difficulty = self.difficulty_profile()
        base = 0.06 + self.current_depth * 0.006 + difficulty.elite_bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.08
        return max(0.0, min(0.42, base))

    def miniboss_chance(self) -> float:
        difficulty = self.difficulty_profile()
        base = 0.015 + self.current_depth * 0.006 + difficulty.miniboss_bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.035
        return max(0.0, min(0.22, base))

    def _shift_color(self, color: Color, shift: Color) -> Color:
        return (
            max(35, min(255, color[0] + shift[0])),
            max(35, min(255, color[1] + shift[1])),
            max(35, min(255, color[2] + shift[2])),
        )

    def _apply_elite_modifier(self, enemy: Enemy) -> None:
        modifier = self.rng.choice(ELITE_MODIFIERS)
        enemy.name = f"{modifier.name} {enemy.name}"
        enemy.elite_modifier = modifier.name
        enemy.telegraph = modifier.description
        enemy.max_hp = max(1, int(enemy.max_hp * modifier.hp_multiplier))
        enemy.hp = enemy.max_hp
        enemy.damage += modifier.damage_bonus
        enemy.speed *= modifier.speed_multiplier
        enemy.xp += modifier.xp_bonus
        enemy.aggro_range += 1.0 if modifier.name == "Runed" else 0.0
        enemy.color = self._shift_color(enemy.color, modifier.color_shift)

    def _make_miniboss(self, x: float, y: float) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        enemy.name = f"Oathbound {enemy.name}"
        enemy.kind = "miniboss"
        enemy.elite_modifier = enemy.elite_modifier or "Oathbound"
        enemy.telegraph = "large readable windups and guaranteed reward"
        enemy.max_hp = int(enemy.max_hp * 1.85)
        enemy.hp = enemy.max_hp
        enemy.damage += 3
        enemy.xp += 34
        enemy.aggro_range += 2.0
        enemy.color = self.theme.accent
        return enemy

    def _make_story_hunter(
        self, x: float, y: float, prefix: str | None = None
    ) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        story_prefix = prefix or "Story-Marked"
        if self.story_state is not None and prefix is None:
            story_prefix = f"{self.story_state.antagonist} Hunter"
        enemy.name = f"{story_prefix} {enemy.name}"
        enemy.elite_modifier = enemy.elite_modifier or "Story-Marked"
        enemy.telegraph = "drawn by unresolved oaths and defiant story choices"
        enemy.max_hp = max(1, int(enemy.max_hp * 1.28))
        enemy.hp = enemy.max_hp
        enemy.damage += max(1, self.current_depth // 2)
        enemy.xp += 14 + self.current_depth * 2
        enemy.aggro_range += 2.5
        enemy.color = self.story_state.accent if self.story_state else self.theme.accent
        return enemy

    def _make_boss(self, x: float, y: float) -> Enemy:
        boss_titles = {
            "Crypt of Ash": "Ashen Gate Tyrant",
            "Fungal Catacombs": "Mycelial Gate Tyrant",
            "Violet Reliquary": "Voidbound Gate Tyrant",
            "Sunken Bastion": "Drowned Gate Tyrant",
            "Frozen Ossuary": "Rimebound Gate Tyrant",
            "Obsidian Foundry": "Forgeheart Gate Tyrant",
            "Moonlit Aquifer": "Moon-Drowned Gate Tyrant",
            "Thornbound Vault": "Thorn-Crowned Gate Tyrant",
        }
        boss_name = boss_titles.get(self.theme.name, "Dread Gate Tyrant")
        if self.story_state is not None:
            boss_name = f"{self.story_state.antagonist} {boss_name}"
        return self._apply_run_modifier(
            Enemy(
                boss_name,
                "boss",
                x,
                y,
                210,
                210,
                1.65,
                18,
                90,
                1.45,
                1.15,
                aggro_range=12.0,
                color=self.theme.accent,
            )
        )

    def _make_loot(self, x: float, y: float) -> Item:
        roll = self.rng.random()
        if roll < 0.24:
            return Item(
                "Minor Healing Potion", "potion", heal=35, rarity="Common", x=x, y=y
            )
        if roll < 0.34:
            return Item(
                "Lesser Mana Potion", "mana_potion", mana=24, rarity="Common", x=x, y=y
            )
        if roll < 0.42:
            return Item("Scroll of Identify", "identify", rarity="Common", x=x, y=y)
        if roll > 0.96 - self.run_modifier.loot_bonus - self.story_effect_value(
            "loot_bonus", 0.0, 0.25
        ):
            return self._make_unique(x, y)
        slot = "weapon" if roll < 0.70 else "armor"
        rarity = "Rare" if self.rng.random() < 0.34 else "Magic"
        if self.rng.random() < 0.20:
            rarity = "Common"
        return self._make_equipment(slot, rarity, x, y)

    def _make_equipment(self, slot: str, rarity: str, x: float, y: float) -> Item:
        if slot == "weapon":
            definition = self.rng.choice(WEAPON_DEFINITIONS)
            item = Item(
                definition.name,
                "weapon",
                power=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        else:
            definition = self.rng.choice(ARMOR_DEFINITIONS)
            item = Item(
                definition.name,
                "armor",
                defense=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        self._apply_affixes(
            item, 0 if rarity == "Common" else 1 if rarity == "Magic" else 2
        )
        curse_chance = (
            0.08
            + (0.08 if self.run_modifier.name == "Cursed Bargains" else 0.0)
            + self.story_effect_value("curse_bonus", 0.0, 0.18)
        )
        if rarity != "Common" and self.rng.random() < curse_chance:
            item.cursed = True
            item.rarity = "Cursed"
            item.affixes.append("Tempting Curse")
            if item.slot == "weapon":
                item.power += 4
            else:
                item.defense += 3
        self._empower_story_relic_item(item)
        item.unidentified = rarity != "Common" and self.rng.random() < 0.45
        return item

    def _empower_story_relic_item(self, item: Item, guaranteed: bool = False) -> None:
        relic_power = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic_power <= 0 or item.slot not in ("weapon", "armor"):
            return
        if "Relic-Touched" in item.affixes:
            return
        if not guaranteed and self.rng.random() > min(0.45, relic_power * 1.35):
            return
        bonus = max(2, int(round(2 + relic_power * 14)))
        if item.slot == "weapon":
            item.power += bonus
        else:
            item.defense += max(2, bonus // 2 + 1)
        if "Relic-Touched" not in item.affixes:
            item.affixes.append("Relic-Touched")
        if self.story_state is not None and not item.unique_effect:
            item.unique_effect = f"echo of {self.story_state.relic_name}"

    def _apply_affixes(self, item: Item, count: int) -> None:
        weapon_affixes = [
            ("Serrated", 3, 0),
            ("Cruel", 5, 0),
            ("Balanced", 2, 0),
            ("Frostbitten", 4, 0),
            ("Zealous", 3, 1),
            ("Vampiric", 4, 0),
            ("Storm-Touched", 5, 0),
        ]
        armor_affixes = [
            ("Reinforced", 0, 2),
            ("Stalwart", 0, 3),
            ("Light", 0, 1),
            ("Sealed", 0, 4),
            ("Thorned", 1, 2),
            ("Grounded", 0, 4),
            ("Regal", 1, 3),
        ]
        utility_affixes = [
            ("of the Fox", 1, 1),
            ("of Warding", 0, 2),
            ("of Force", 2, 0),
            ("of the Deep", 0, 3),
            ("of Ember", 3, 0),
            ("of Cinders", 4, -1),
            ("of the Moon", 1, 3),
        ]
        pool = weapon_affixes if item.slot == "weapon" else armor_affixes
        pool = pool + utility_affixes
        for name, power, defense in self.rng.sample(pool, k=min(count, len(pool))):
            item.affixes.append(name)
            item.power += power
            item.defense += defense

    def _make_unique(self, x: float, y: float) -> Item:
        unique_roll = self.rng.random()
        if unique_roll < 0.42:
            return Item(
                "Emberbrand",
                "weapon",
                power=12,
                rarity="Unique",
                x=x,
                y=y,
                affixes=["Serrated", "of Force"],
                unidentified=self.rng.random() < 0.35,
                unique_effect="embers on hit",
            )
        if unique_roll < 0.72:
            return Item(
                "Frostwake",
                "weapon",
                power=10,
                rarity="Unique",
                x=x,
                y=y,
                affixes=["Frostbitten", "Balanced"],
                unidentified=self.rng.random() < 0.35,
                unique_effect="chill on hit",
            )
        return Item(
            "Bulwark of the First Gate",
            "armor",
            defense=8,
            rarity="Unique",
            x=x,
            y=y,
            affixes=["Reinforced", "of Warding"],
            unidentified=self.rng.random() < 0.35,
            unique_effect="steadfast bulwark",
        )

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
                    if self.state == "playing" and self.inventory_open:
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
                elif event.key == pygame.K_i and self.state == "playing":
                    self.inventory_open = not self.inventory_open
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
                    self.state = "archetype_select"
                elif event.key == pygame.K_e and self.state == "playing":
                    self.interact()
                elif event.key == pygame.K_q and self.state == "playing":
                    self.toggle_quest_info_visibility()
                elif event.key == pygame.K_r and self.state == "playing":
                    self.use_first_potion()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self.update_player_aim()
                    self.player_melee_attack()
                elif event.key == pygame.K_f and self.state == "playing":
                    self.update_player_aim()
                    self.player_cast_bolt()
                elif event.key == pygame.K_c and self.state == "playing":
                    self.player_cast_nova()
                elif event.key == pygame.K_LCTRL and self.state == "playing":
                    self.update_player_aim()
                    self.player_dash()
                elif pygame.K_1 <= event.key <= pygame.K_9 and self.state == "playing":
                    index = event.key - pygame.K_1
                    guest = None if self.inventory_open else self.nearby_story_guest()
                    if guest and index < len(guest.choices):
                        self.resolve_story_choice(guest, index)
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
        if self.story_intro_pending:
            self.update_floaters(dt)
            return
        self.update_player_aim()
        self.update_player(dt)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_traps(dt)
        self.update_secrets()
        self.update_floaters(dt)

        if self.player.hp <= 0 and self.state == "playing":
            self.state = "dead"
            self.audio.stop_music()
            self.play_sfx("death")
            self.delete_save()

    def update_player_aim(self) -> None:
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])
        dy = float(keys[pygame.K_DOWN]) - float(keys[pygame.K_UP])
        if dx or dy:
            length = math.hypot(dx, dy)
            self.player.facing_x = dx / length
            self.player.facing_y = dy / length
        else:
            self.face_player_toward_screen_point(*pygame.mouse.get_pos())

    def face_player_toward_screen_point(self, sx: int, sy: int) -> tuple[float, float]:
        target_x, target_y = self.screen_to_world(sx, sy)
        dx = target_x - self.player.x
        dy = target_y - self.player.y
        distance = math.hypot(dx, dy)
        if distance > 0.05:
            self.player.facing_x = dx / distance
            self.player.facing_y = dy / distance
        return dx, dy

    def skill_names(self) -> tuple[str, str, str, str]:
        names = {
            "Warden": ("Shield Bash", "Guard Bolt", "Bulwark Wave", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Smoke Burst", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Blood Nova", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Snare Nova", "Vault"),
        }
        return names.get(self.player.class_name, ("Slash", "Bolt", "Nova", "Dash"))

    def skill_color(self) -> Color:
        colors = {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }
        return colors.get(self.player.class_name, (120, 210, 255))

    def grant_skill_upgrade(self, reason: str = "level up") -> bool:
        choices = [
            upgrade
            for upgrade in SKILL_UPGRADES
            if upgrade.archetype == self.player.class_name
            and upgrade.key not in self.player.skill_upgrades
        ]
        if not choices:
            return False
        upgrade = self.rng.choice(choices)
        self.player.skill_upgrades.append(upgrade.key)
        self.player.melee_bonus += upgrade.melee_bonus
        self.player.spell_bonus += upgrade.spell_bonus
        self.player.armor_bonus += upgrade.armor_bonus
        self.player.max_hp += upgrade.max_hp_bonus
        self.player.hp = min(self.player.max_hp, self.player.hp + upgrade.max_hp_bonus)
        self.player.max_mana += upgrade.max_mana_bonus
        self.player.mana = min(
            self.player.max_mana, self.player.mana + upgrade.max_mana_bonus
        )
        self.player.max_stamina += upgrade.max_stamina_bonus
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + upgrade.max_stamina_bonus
        )
        self.player.speed += upgrade.speed_bonus
        self.run_stats.upgrades_chosen += 1
        self.floaters.append(
            FloatingText(
                f"{upgrade.name}: {reason}",
                self.player.x,
                self.player.y - 0.65,
                self.skill_color(),
                ttl=1.8,
            )
        )
        return True

    def melee_stamina_cost(self) -> int:
        cost = 9 if self.player.class_name == "Rogue" else 12
        if self.player.has_upgrade("rogue_precision"):
            cost -= 2
        return max(5, cost)

    def melee_cooldown(self) -> float:
        cooldown = 0.30 if self.player.class_name == "Rogue" else 0.36
        if self.player.has_upgrade("warden_bulwark"):
            cooldown += 0.02
        return cooldown

    def bolt_mana_cost(self) -> int:
        cost = 7 if self.player.class_name in ("Arcanist", "Ranger") else 10
        if self.player.has_upgrade("arcanist_focus"):
            cost -= 1
        return max(4, cost)

    def bolt_cooldown(self) -> float:
        return 0.38 if self.player.class_name in ("Arcanist", "Ranger") else 0.48

    def nova_mana_cost(self) -> int:
        cost = 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18
        if self.player.has_upgrade("acolyte_veil"):
            cost -= 2
        return max(8, cost)

    def nova_cooldown(self) -> float:
        return 2.65 if self.player.class_name == "Arcanist" else 3.2

    def dash_stamina_cost(self) -> int:
        cost = 12 if self.player.class_name in ("Rogue", "Ranger") else 18
        if self.player.has_upgrade("rogue_smoke"):
            cost -= 2
        return max(8, cost)

    def dash_cooldown(self) -> float:
        return 0.62 if self.player.class_name == "Ranger" else 0.85

    def take_player_damage(self, raw_damage: int, source: str = "hit") -> int:
        rogue_evade = 0.18 if self.player.has_upgrade("rogue_smoke") else 0.12
        if self.player.class_name == "Rogue" and self.rng.random() < rogue_evade:
            self.floaters.append(
                FloatingText(
                    "Evaded", self.player.x, self.player.y - 0.2, (170, 220, 170)
                )
            )
            return 0
        armor_bonus = (
            2 if self.player.class_name == "Warden" and source == "melee" else 0
        )
        amount = max(1, raw_damage - self.player.armor() - armor_bonus)
        if self.player.has_upgrade("warden_riposte") and source == "melee":
            amount = max(1, amount - 2)
        if self.player.class_name == "Acolyte" and self.player.mana >= 4:
            self.player.mana -= 4
            amount = max(
                1, amount - (5 if self.player.has_upgrade("acolyte_veil") else 3)
            )
        resist = self.story_effect_value("damage_resist", 0.0, 0.35)
        if resist > 0:
            before_resist = amount
            amount = max(1, int(round(amount * (1.0 - resist))))
            if amount < before_resist:
                self.floaters.append(
                    FloatingText(
                        f"Story ward -{before_resist - amount}",
                        self.player.x,
                        self.player.y - 0.45,
                        self.story_state.accent
                        if self.story_state
                        else (190, 150, 245),
                        ttl=0.9,
                    )
                )
        self.player.hp -= amount
        self.run_stats.damage_taken += amount
        flash = (160, 35, 32) if amount >= self.player.max_hp * 0.18 else (105, 24, 28)
        self.player_hit_flash = max(
            self.player_hit_flash, 0.22 if amount < self.player.max_hp * 0.18 else 0.32
        )
        self.trigger_screen_flash(
            flash, 0.18 if amount < self.player.max_hp * 0.18 else 0.30
        )
        self.add_impact(
            self.player.x,
            self.player.y,
            (245, 95, 70),
            ttl=0.34,
            radius=0.42,
            kind="blood",
        )
        if self.player.hp > 0 and self.player.hp <= self.player.max_hp * 0.25:
            self.floaters.append(
                FloatingText(
                    "Low health",
                    self.player.x,
                    self.player.y - 0.7,
                    (245, 95, 70),
                    ttl=1.0,
                )
            )
        return amount

    def update_player(self, dt: float) -> None:
        self.player.moving = False
        if pygame.mouse.get_pressed()[0]:
            dx, dy = self.face_player_toward_screen_point(*pygame.mouse.get_pos())
            distance = math.hypot(dx, dy)
            if distance > 0.18:
                self.move_actor(
                    self.player,
                    (dx / distance) * self.player.speed * dt,
                    (dy / distance) * self.player.speed * dt,
                )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
        self.player.dash_timer = max(0.0, self.player.dash_timer - dt)
        self.player.nova_timer = max(0.0, self.player.nova_timer - dt)
        stamina_regen = 38 if self.player.class_name == "Ranger" else 30
        mana_regen = 8 if self.player.class_name == "Arcanist" else 5
        if self.player.has_upgrade("arcanist_focus"):
            mana_regen += 3
        if self.player.has_upgrade("ranger_snare"):
            stamina_regen += 4
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + stamina_regen * dt
        )
        self.player.mana = min(self.player.max_mana, self.player.mana + mana_regen * dt)

    def move_actor(self, actor: Player | Enemy, dx: float, dy: float) -> None:
        old_x, old_y = actor.x, actor.y
        new_x = actor.x + dx
        if not self.dungeon.blocked_for_radius(new_x, actor.y):
            actor.x = new_x
        new_y = actor.y + dy
        if not self.dungeon.blocked_for_radius(actor.x, new_y):
            actor.y = new_y
        self.resolve_actor_contacts(actor)

        actual_dx = actor.x - old_x
        actual_dy = actor.y - old_y
        distance = math.hypot(actual_dx, actual_dy)
        if distance > 0.0001:
            actor.moving = True
            target_x = actual_dx / distance
            target_y = actual_dy / distance
            blend = 0.38
            smoothed_x = actor.move_x * (1.0 - blend) + target_x * blend
            smoothed_y = actor.move_y * (1.0 - blend) + target_y * blend
            smoothed_length = math.hypot(smoothed_x, smoothed_y)
            if smoothed_length > 0.001:
                actor.move_x = smoothed_x / smoothed_length
                actor.move_y = smoothed_y / smoothed_length
            else:
                actor.move_x = target_x
                actor.move_y = target_y
            actor.anim_time += distance * WALK_ANIMATION_RATE

    def actor_hit_radius(self, actor: Player | Enemy) -> float:
        if isinstance(actor, Player):
            return PLAYER_HIT_RADIUS
        return self.enemy_hit_radius(actor)

    def enemy_hit_radius(self, enemy: Enemy) -> float:
        if enemy.kind == "boss":
            return BOSS_HIT_RADIUS
        if enemy.name in ("Gate Warden", "Crypt Brute"):
            return LARGE_ENEMY_HIT_RADIUS
        return ENEMY_HIT_RADIUS

    def contact_distance(self, enemy: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.enemy_hit_radius(enemy)

    def resolve_actor_contacts(self, actor: Player | Enemy) -> None:
        others: list[Player | Enemy]
        if isinstance(actor, Player):
            others = list(self.enemies)
        else:
            others = [
                self.player,
                *(enemy for enemy in self.enemies if enemy is not actor),
            ]

        for other in others:
            dx = actor.x - other.x
            dy = actor.y - other.y
            distance = math.hypot(dx, dy)
            min_distance = self.actor_hit_radius(actor) + self.actor_hit_radius(other)
            if distance >= min_distance:
                continue

            if distance > 0.001:
                nx, ny = dx / distance, dy / distance
            else:
                nx, ny = -actor.facing_x, -actor.facing_y
                if math.hypot(nx, ny) <= 0.001:
                    nx, ny = 1.0, 0.0

            target_x = other.x + nx * min_distance
            target_y = other.y + ny * min_distance
            if not self.dungeon.blocked_for_radius(target_x, actor.y):
                actor.x = target_x
            if not self.dungeon.blocked_for_radius(actor.x, target_y):
                actor.y = target_y

    def update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.moving = False
            enemy.attack_timer = max(0.0, enemy.attack_timer - dt)
            dx = self.player.x - enemy.x
            dy = self.player.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > enemy.aggro_range:
                continue
            nx, ny = (dx / distance, dy / distance) if distance > 0.001 else (0.0, 0.0)
            if distance > 0.001:
                enemy.facing_x = nx
                enemy.facing_y = ny

            if enemy.kind == "boss":
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                if 2.0 < distance <= 6.0 and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
                elif distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)
            elif enemy.kind == "ranged":
                if 3.5 < distance:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                elif distance < 2.5:
                    self.move_actor(
                        enemy, -nx * enemy.speed * dt, -ny * enemy.speed * dt
                    )
                if distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
            else:
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                elif enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)

    def enemy_melee(self, enemy: Enemy) -> None:
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "melee"
        raw = enemy.damage + self.rng.randrange(-2, 3)
        amount = self.take_player_damage(raw, source="melee")
        self.floaters.append(
            FloatingText(
                f"-{amount}", self.player.x, self.player.y - 0.2, (235, 90, 80)
            )
        )
        self.slashes.append(
            (
                (enemy.x + self.player.x) * 0.5,
                (enemy.y + self.player.y) * 0.5,
                0.14,
                enemy.facing_x,
                enemy.facing_y,
            )
        )
        self.add_impact(
            (enemy.x + self.player.x) * 0.5,
            (enemy.y + self.player.y) * 0.5,
            (255, 180, 130),
            ttl=0.26,
            radius=0.34,
            kind="slash",
        )

    def enemy_cast(self, enemy: Enemy, nx: float, ny: float) -> None:
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "cast"
        projectile_color = (245, 100, 235) if enemy.elite_modifier else (180, 80, 220)
        if enemy.kind in ("boss", "miniboss"):
            projectile_color = self.theme.accent
        self.add_impact(
            enemy.x, enemy.y, projectile_color, ttl=0.28, radius=0.36, kind="cast"
        )
        self.projectiles.append(
            Projectile(
                enemy.x,
                enemy.y,
                nx * 6.0,
                ny * 6.0,
                enemy.damage,
                "enemy",
                projectile_color,
                ttl=1.8,
            )
        )

    def update_projectiles(self, dt: float) -> None:
        kept: list[Projectile] = []
        for projectile in self.projectiles:
            if not projectile.update(dt, self.dungeon):
                continue
            if projectile.owner == "player":
                hit = self.first_enemy_near(
                    projectile.x, projectile.y, PLAYER_PROJECTILE_HIT_RADIUS
                )
                if hit:
                    self.add_impact(
                        projectile.x,
                        projectile.y,
                        projectile.color,
                        ttl=0.32,
                        radius=0.38,
                        kind="burst",
                    )
                    self.damage_enemy(
                        hit,
                        projectile.damage,
                        knockback_from=(projectile.vx, projectile.vy),
                    )
                    continue
            else:
                if (
                    math.hypot(
                        projectile.x - self.player.x, projectile.y - self.player.y
                    )
                    < ENEMY_PROJECTILE_HIT_RADIUS
                ):
                    amount = self.take_player_damage(
                        projectile.damage, source="projectile"
                    )
                    self.floaters.append(
                        FloatingText(
                            f"-{amount}",
                            self.player.x,
                            self.player.y - 0.2,
                            (235, 90, 80),
                        )
                    )
                    self.add_impact(
                        projectile.x,
                        projectile.y,
                        projectile.color,
                        ttl=0.34,
                        radius=0.42,
                        kind="burst",
                    )
                    continue
            kept.append(projectile)
        self.projectiles = kept

    def update_traps(self, _dt: float) -> None:
        for trap in self.traps:
            if not trap.active:
                continue
            if math.hypot(trap.x - self.player.x, trap.y - self.player.y) > 0.55:
                continue
            trap.active = False
            amount = self.take_player_damage(trap.damage, source="trap")
            self.run_stats.traps_triggered += 1
            self.floaters.append(
                FloatingText(
                    f"{trap.kind}! -{amount}",
                    self.player.x,
                    self.player.y - 0.2,
                    (245, 95, 70),
                    ttl=1.2,
                )
            )
            self.add_impact(
                trap.x, trap.y, (245, 95, 70), ttl=0.46, radius=0.58, kind="burst"
            )
            self.play_sfx("trap")

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

    def player_melee_attack(self) -> None:
        stamina_cost = self.melee_stamina_cost()
        if self.player.melee_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.melee_timer = self.melee_cooldown()
        self.player.stamina -= stamina_cost
        self.set_player_action_visual("attack", 0.20)
        target = self.enemy_in_melee_arc()
        if target:
            tx = (self.player.x + target.x) * 0.5
            ty = (self.player.y + target.y) * 0.5
        else:
            tx = self.player.x + self.player.facing_x * 0.9
            ty = self.player.y + self.player.facing_y * 0.9
        self.slashes.append((tx, ty, 0.18, self.player.facing_x, self.player.facing_y))
        if target:
            targets = [target]
            if self.player.class_name == "Warden":
                reach = 0.35 if self.player.has_upgrade("warden_bulwark") else 0.18
                limit = 4 if self.player.has_upgrade("warden_bulwark") else 3
                targets = self.enemies_in_melee_arc(reach_bonus=reach)[:limit]
            for index, enemy in enumerate(list(targets)):
                damage = self.player.melee_damage() + self.rng.randrange(-3, 5)
                if index > 0:
                    damage = max(1, int(damage * 0.62))
                crit_chance = (
                    0.30 if self.player.has_upgrade("rogue_precision") else 0.22
                )
                if (
                    self.player.class_name == "Rogue"
                    and self.rng.random() < crit_chance
                ):
                    damage = int(
                        damage
                        * (1.95 if self.player.has_upgrade("rogue_precision") else 1.75)
                    )
                    self.floaters.append(
                        FloatingText(
                            "Critical", enemy.x, enemy.y - 0.45, (255, 225, 120)
                        )
                    )
                if self.player.class_name == "Warden":
                    enemy.attack_timer = max(enemy.attack_timer, 0.35)
                damage = self.apply_story_player_damage(damage)
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=(self.player.facing_x, self.player.facing_y),
                )
                if self.player.class_name == "Acolyte":
                    leech = 4 if self.player.has_upgrade("acolyte_sanguine") else 2
                    self.player.hp = min(self.player.max_hp, self.player.hp + leech)

    def player_cast_bolt(self) -> None:
        mana_cost = self.bolt_mana_cost()
        if self.player.bolt_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.bolt_timer = self.bolt_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.24)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.28,
            radius=0.34,
            kind="cast",
        )
        damage = 14 + self.player.level * 2 + self.player.spell_bonus
        if self.player.class_name == "Acolyte":
            damage += max(0, self.player.max_hp - self.player.hp) // 12
        damage = self.apply_story_player_damage(damage, spell=True)
        self.apply_story_blood_price("bolt")
        angles = [0.0]
        if self.player.class_name == "Ranger":
            angles = (
                [-0.28, -0.12, 0.0, 0.12, 0.28]
                if self.player.has_upgrade("ranger_volley")
                else [-0.16, 0.0, 0.16]
            )
        elif self.player.class_name == "Arcanist":
            angles = (
                [-0.12, 0.0, 0.12]
                if self.player.has_upgrade("arcanist_splinter")
                else [-0.06, 0.06]
            )
        for angle in angles:
            dx = self.player.facing_x * math.cos(
                angle
            ) - self.player.facing_y * math.sin(angle)
            dy = self.player.facing_x * math.sin(
                angle
            ) + self.player.facing_y * math.cos(angle)
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    dx * 9.0,
                    dy * 9.0,
                    damage if abs(angle) <= 0.001 else max(1, damage - 4),
                    "player",
                    (70, 165, 255),
                    ttl=1.55 if self.player.has_upgrade("arcanist_splinter") else 1.4,
                )
            )

    def player_cast_nova(self) -> None:
        mana_cost = self.nova_mana_cost()
        if self.player.nova_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.nova_timer = self.nova_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.32)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.48,
            radius=0.82,
            kind="cast",
        )
        self.apply_story_blood_price("nova")
        hits = 0
        for enemy in list(self.enemies):
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            radius = 2.85 if self.player.class_name == "Arcanist" else 2.45
            if self.player.has_upgrade("arcanist_focus"):
                radius += 0.35
            if distance <= radius:
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                if self.player.class_name == "Ranger":
                    snare_time = (
                        1.25 if self.player.has_upgrade("ranger_snare") else 0.8
                    )
                    enemy.attack_timer = max(enemy.attack_timer, snare_time)
                if self.player.class_name == "Acolyte":
                    leech = 5 if self.player.has_upgrade("acolyte_sanguine") else 3
                    self.player.hp = min(self.player.max_hp, self.player.hp + leech)
                damage = self.apply_story_player_damage(damage, spell=True)
                direction = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (self.player.facing_x, self.player.facing_y)
                )
                self.damage_enemy(enemy, damage, knockback_from=direction)
        self.floaters.append(
            FloatingText(
                f"{self.skill_names()[2]}{f' x{hits}' if hits else ''}",
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
                ttl=0.9,
            )
        )
        for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
            self.slashes.append(
                (
                    self.player.x + math.cos(angle) * 0.9,
                    self.player.y + math.sin(angle) * 0.9,
                    0.18,
                    math.cos(angle),
                    math.sin(angle),
                )
            )

    def player_dash(self) -> None:
        stamina_cost = self.dash_stamina_cost()
        if self.player.dash_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.dash_timer = self.dash_cooldown()
        self.player.stamina -= stamina_cost
        start_x, start_y = self.player.x, self.player.y
        self.set_player_action_visual("dash", 0.22)
        self.add_impact(
            start_x, start_y, self.skill_color(), ttl=0.24, radius=0.34, kind="dash"
        )
        steps = 11 if self.player.class_name == "Ranger" else 8
        if self.player.has_upgrade("rogue_smoke"):
            steps += 2
        for _ in range(steps):
            self.move_actor(
                self.player,
                self.player.facing_x * 0.20,
                self.player.facing_y * 0.20,
            )
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.26,
            radius=0.42,
            kind="dash",
        )
        self.floaters.append(
            FloatingText(
                self.skill_names()[3],
                self.player.x,
                self.player.y - 0.4,
                self.skill_color(),
                ttl=0.45,
            )
        )

    def enemies_in_melee_arc(self, reach_bonus: float = 0.0) -> list[Enemy]:
        candidates: list[tuple[float, Enemy]] = []
        for enemy in self.enemies:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance > PLAYER_MELEE_RANGE + reach_bonus or distance < 0.001:
                continue
            dot = (dx / distance) * self.player.facing_x + (
                dy / distance
            ) * self.player.facing_y
            if dot > PLAYER_MELEE_ARC_DOT:
                candidates.append((distance, enemy))
        return [
            enemy for _distance, enemy in sorted(candidates, key=lambda entry: entry[0])
        ]

    def enemy_in_melee_arc(self) -> Enemy | None:
        enemies = self.enemies_in_melee_arc()
        return enemies[0] if enemies else None

    def first_enemy_near(self, x: float, y: float, radius: float) -> Enemy | None:
        for enemy in self.enemies:
            hit_radius = radius + self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS
            if math.hypot(enemy.x - x, enemy.y - y) <= hit_radius:
                return enemy
        return None

    def damage_enemy(
        self, enemy: Enemy, amount: int, knockback_from: tuple[float, float]
    ) -> None:
        enemy.hp -= amount
        self.enemy_hit_flashes[id(enemy)] = 0.22 if enemy.kind != "boss" else 0.32
        hit_color = self.theme.accent if enemy.kind == "boss" else (255, 210, 120)
        self.floaters.append(
            FloatingText(f"-{amount}", enemy.x, enemy.y - 0.2, hit_color)
        )
        self.add_impact(
            enemy.x,
            enemy.y,
            hit_color,
            ttl=0.32 if enemy.kind != "boss" else 0.46,
            radius=0.36 if enemy.kind != "boss" else 0.58,
            kind="hit",
        )
        kx, ky = knockback_from
        length = math.hypot(kx, ky)
        if length > 0.001:
            self.move_actor(enemy, (kx / length) * 0.16, (ky / length) * 0.16)
        if enemy.hp <= 0:
            self.kill_enemy(enemy)
        else:
            self.play_sfx("hit")

    def kill_enemy(self, enemy: Enemy) -> None:
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)
        self.enemy_hit_flashes.pop(id(enemy), None)
        self.run_stats.kills += 1
        death_color = (
            self.theme.accent if enemy.kind in ("boss", "miniboss") else enemy.color
        )
        self.add_impact(
            enemy.x,
            enemy.y,
            death_color,
            ttl=0.58 if enemy.kind != "boss" else 0.82,
            radius=0.56 if enemy.kind != "boss" else 1.05,
            kind="death",
        )
        if enemy.elite_modifier or enemy.kind in ("boss", "miniboss"):
            self.add_impact(
                enemy.x,
                enemy.y,
                death_color,
                ttl=0.48,
                radius=0.66 if enemy.kind != "boss" else 1.15,
                kind="burst",
            )
        if enemy.kind == "boss":
            self.run_stats.boss_killed = True
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            self.items.append(self._make_unique(drop_x, drop_y))
            self.floaters.append(
                FloatingText(
                    "Gate seal broken",
                    enemy.x,
                    enemy.y - 0.5,
                    self.theme.accent,
                    ttl=1.6,
                )
            )
            self.trigger_screen_flash(self.theme.accent, 0.36)
            self.add_impact(
                enemy.x, enemy.y, self.theme.accent, ttl=0.72, radius=0.9, kind="burst"
            )
            self.play_sfx("boss")
        elif enemy.kind == "miniboss":
            self.run_stats.minibosses_killed += 1
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            self.items.append(
                self._make_equipment(
                    self.rng.choice(("weapon", "armor")), "Rare", drop_x, drop_y
                )
            )
        elif enemy.elite_modifier:
            self.run_stats.elites_killed += 1
        xp_gain = max(
            1, int(enemy.xp * (1.0 + self.story_effect_value("xp_bonus", 0.0, 0.35)))
        )
        if self.player.gain_xp(xp_gain):
            upgraded = self.grant_skill_upgrade(reason="level up")
            self.floaters.append(
                FloatingText(
                    "LEVEL UP" if not upgraded else "LEVEL UP · SKILL GROWN",
                    self.player.x,
                    self.player.y - 0.6,
                    (120, 230, 150),
                    ttl=1.4,
                )
            )
        healing_echo = self.story_effect_value("healing_echo", 0.0, 1.0)
        if (
            healing_echo > 0
            and self.player.hp < self.player.max_hp
            and self.rng.random() < min(1.0, healing_echo)
        ):
            healed = min(
                self.player.max_hp - self.player.hp,
                max(2, int(enemy.xp * 0.12) + self.current_depth // 2),
            )
            self.player.hp += healed
            self.player.mana = min(
                self.player.max_mana, self.player.mana + max(1, healed // 2)
            )
            self.floaters.append(
                FloatingText(
                    f"Story echo +{healed}",
                    self.player.x,
                    self.player.y - 0.55,
                    self.story_state.accent if self.story_state else (170, 225, 190),
                    ttl=1.0,
                )
            )
        if self.rng.random() < 0.45:
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            self.items.append(self._make_loot(drop_x, drop_y))
        self.save_run()

    def drop_position_near(self, x: float, y: float) -> tuple[float, float]:
        offsets = (
            (0.0, 0.0),
            (1.15, 0.0),
            (-1.15, 0.0),
            (0.0, 1.15),
            (0.0, -1.15),
            (1.15, 1.15),
            (-1.15, 1.15),
            (1.15, -1.15),
            (-1.15, -1.15),
        )
        stair_x, stair_y = self.dungeon.stairs[0] + 0.5, self.dungeon.stairs[1] + 0.5
        for ox, oy in offsets:
            px, py = x + ox, y + oy
            if math.hypot(px - stair_x, py - stair_y) < 1.05:
                continue
            if not self.dungeon.blocked_for_radius(px, py, radius=0.22):
                return px, py
        return x, y

    def player_near_stairs(self) -> bool:
        return (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        )

    def interact(self) -> None:
        if self.story_intro_pending:
            self.floaters.append(
                FloatingText(
                    "Choose 1-3 to answer the guest first",
                    self.player.x,
                    self.player.y - 0.5,
                    self.story_state.accent if self.story_state else self.theme.accent,
                    ttl=1.1,
                )
            )
            return
        story_relic = self.nearby_story_relic()
        if story_relic is not None:
            self.collect_story_relic(story_relic)
            return
        if self.player_near_stairs():
            if self.current_depth < DUNGEON_DEPTH:
                self.descend_to_next_depth()
                return
            if self.boss_alive():
                self.floaters.append(
                    FloatingText(
                        "The gate is sealed by its tyrant",
                        self.player.x,
                        self.player.y - 0.5,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )
                return
            self.state = "victory"
            self.audio.stop_music()
            self.play_sfx("victory")
            self.delete_save()
            return
        guest = self.nearby_story_guest()
        if guest:
            self.talk_to_story_guest(guest)
            return
        secret = self.nearby_secret()
        if secret:
            self.open_secret(secret)
            return
        shrine = self.nearby_shrine()
        if shrine:
            self.activate_shrine(shrine)
            return
        nearest = self.nearby_item()
        if nearest:
            if nearest.slot == "story_relic":
                self.collect_story_relic(nearest)
                return
            if len(self.player.inventory) >= MAX_INVENTORY:
                self.floaters.append(
                    FloatingText(
                        "Inventory full",
                        self.player.x,
                        self.player.y - 0.4,
                        (235, 210, 120),
                    )
                )
                return
            self.items.remove(nearest)
            self.player.inventory.append(nearest)
            self.run_stats.loot_picked_up += 1
            self.floaters.append(
                FloatingText(
                    f"Picked up {nearest.display_name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (210, 230, 180),
                    ttl=1.2,
                )
            )
            self.play_sfx("pickup")
            self.save_run()

    def collect_story_relic(self, relic: Item) -> None:
        if relic in self.items:
            self.items.remove(relic)
        self.story_relic_collected = True
        self.story_relic_position = None
        guest = self.current_story_guest_for_depth()
        message = "Guest relic recovered"
        if guest is not None:
            message = f"Relic points to {guest.name}"
        self.player.mana = min(self.player.max_mana, self.player.mana + 6)
        self.player.stamina = min(self.player.max_stamina, self.player.stamina + 12)
        self.floaters.append(
            FloatingText(
                message,
                self.player.x,
                self.player.y - 0.5,
                self.story_state.accent if self.story_state else self.theme.accent,
                ttl=1.4,
            )
        )
        self.add_impact(
            relic.x,
            relic.y,
            self.story_state.accent if self.story_state else self.theme.accent,
            ttl=0.62,
            radius=0.62,
            kind="burst",
        )
        if self.story_state is not None:
            self.story_state.log.append(
                f"Depth {self.current_depth}: Guest relic recovered — {message}."
            )
            del self.story_state.log[:-12]
        self.play_sfx("pickup")
        self.save_run()

    def nearby_item(self) -> Item | None:
        nearby = [
            item
            for item in self.items
            if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0
        ]
        return min(
            nearby,
            key=lambda item: math.hypot(item.x - self.player.x, item.y - self.player.y),
            default=None,
        )

    def nearby_story_relic(self) -> Item | None:
        nearby = [
            item
            for item in self.items
            if item.slot == "story_relic"
            and math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0
        ]
        return min(
            nearby,
            key=lambda item: math.hypot(item.x - self.player.x, item.y - self.player.y),
            default=None,
        )

    def nearby_trap_warning(self) -> Trap | None:
        nearby = [
            trap
            for trap in self.traps
            if trap.active
            and math.hypot(trap.x - self.player.x, trap.y - self.player.y) < 1.35
        ]
        return min(
            nearby,
            key=lambda trap: math.hypot(trap.x - self.player.x, trap.y - self.player.y),
            default=None,
        )

    def nearby_secret(self) -> SecretCache | None:
        nearby = [
            secret
            for secret in self.secrets
            if secret.revealed
            and not secret.opened
            and math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.1
        ]
        return min(
            nearby,
            key=lambda secret: math.hypot(
                secret.x - self.player.x, secret.y - self.player.y
            ),
            default=None,
        )

    def open_secret(self, secret: SecretCache) -> None:
        secret.opened = True
        self.run_stats.secrets_opened += 1
        if secret.kind == "Forgotten Skill Altar":
            self.grant_skill_upgrade(reason="forgotten altar")
            message = "Forgotten altar deepens your build"
        elif secret.kind == "Moonlit Bargain":
            self.player.hp = max(1, self.player.hp - max(6, self.player.max_hp // 8))
            self.items.append(
                self._make_equipment(
                    self.rng.choice(("weapon", "armor")), "Rare", secret.x, secret.y
                )
            )
            message = "Moonlit bargain takes blood for gear"
        elif secret.kind == "Cursed Reliquary" and self.rng.random() < 0.55:
            self.enemies.append(self._make_miniboss(secret.x + 0.3, secret.y + 0.3))
            message = "Reliquary wakes a sworn guardian"
        else:
            drops = 2 if "Stash" in secret.kind or secret.kind == "Sealed Armory" else 1
            for _ in range(drops):
                if secret.kind == "Sealed Armory":
                    self.items.append(
                        self._make_equipment(
                            self.rng.choice(("weapon", "armor")),
                            "Magic",
                            secret.x,
                            secret.y,
                        )
                    )
                else:
                    self.items.append(self._make_loot(secret.x, secret.y))
            message = f"Opened {secret.kind}"
        color = SECRET_HINTS.get(
            secret.kind, InteractionHint(secret.kind, message, self.theme.accent)
        ).color
        self.floaters.append(
            FloatingText(message, secret.x, secret.y - 0.3, color, ttl=1.4)
        )
        self.add_impact(secret.x, secret.y, color, ttl=0.52, radius=0.62, kind="burst")
        self.play_sfx("secret")
        self.save_run()

    def boss_alive(self) -> bool:
        return any(enemy.kind == "boss" for enemy in self.enemies)

    def boss_enemy(self) -> Enemy | None:
        return next((enemy for enemy in self.enemies if enemy.kind == "boss"), None)

    def nearby_shrine(self) -> Shrine | None:
        nearby = [
            shrine
            for shrine in self.shrines
            if not shrine.used
            and math.hypot(shrine.x - self.player.x, shrine.y - self.player.y) < 1.15
        ]
        return min(
            nearby,
            key=lambda shrine: math.hypot(
                shrine.x - self.player.x, shrine.y - self.player.y
            ),
            default=None,
        )

    def activate_shrine(self, shrine: Shrine) -> None:
        shrine.used = True
        self.run_stats.shrines_used += 1
        if shrine.kind == "Mending Shrine":
            self.player.hp = self.player.max_hp
            self.player.mana = self.player.max_mana
            message = "Shrine restored you"
        elif shrine.kind == "Insight Shrine":
            identified = self.identify_all_items()
            message = (
                f"Shrine revealed {identified} item{'s' if identified != 1 else ''}"
            )
        elif shrine.kind == "War Shrine":
            leveled = self.player.gain_xp(25)
            self.player.stamina = self.player.max_stamina
            message = "War Shrine grants focus"
            if leveled:
                message = "War Shrine grants a level"
        elif shrine.kind == "Haste Shrine":
            self.player.stamina = self.player.max_stamina
            self.player.dash_timer = 0.0
            self.player.speed += 0.18
            message = "Haste Shrine quickens your stride"
        elif shrine.kind == "Oath Shrine":
            granted = self.grant_skill_upgrade(reason="oath shrine")
            message = (
                "Oath Shrine grants a new technique"
                if granted
                else "Oath Shrine finds no path left"
            )
        elif shrine.kind == "Twilight Shrine":
            self.player.hp = max(1, self.player.hp - max(5, self.player.max_hp // 10))
            self.items.append(self._make_unique(self.player.x, self.player.y))
            message = "Twilight Shrine trades blood for a relic"
        else:
            self.items.append(self._make_loot(self.player.x, self.player.y))
            self.items.append(
                self._make_loot(self.player.x + 0.25, self.player.y + 0.25)
            )
            message = "Fortune Shrine spills offerings"
        color = SHRINE_HINTS.get(
            shrine.kind, InteractionHint(shrine.kind, message, (245, 215, 120))
        ).color
        self.floaters.append(
            FloatingText(message, self.player.x, self.player.y - 0.5, color, ttl=1.3)
        )
        self.add_impact(shrine.x, shrine.y, color, ttl=0.58, radius=0.68, kind="burst")
        self.play_sfx("shrine")
        self.save_run()

    def inventory_category(self, item: Item) -> int:
        order = {
            "weapon": 0,
            "armor": 1,
            "potion": 2,
            "mana_potion": 3,
            "identify": 4,
        }
        return order.get(item.slot, 9)

    def inventory_power_score(self, item: Item) -> int:
        if item.slot == "weapon":
            return item.power
        if item.slot == "armor":
            return item.defense
        if item.slot == "potion":
            return item.heal
        if item.slot == "mana_potion":
            return item.mana
        return 0

    def inventory_rarity_rank(self, item: Item) -> int:
        return {
            "Common": 0,
            "Magic": 1,
            "Rare": 2,
            "Cursed": 3,
            "Unique": 4,
            "Unidentified": 5,
        }.get(item.visible_rarity, 0)

    def inventory_sort_key(self, item: Item) -> tuple[int, int, int, str]:
        if self.inventory_sort_mode == "rarity":
            return (
                -self.inventory_rarity_rank(item),
                self.inventory_category(item),
                -self.inventory_power_score(item),
                item.display_name,
            )
        if self.inventory_sort_mode == "power":
            return (
                self.inventory_category(item),
                -self.inventory_power_score(item),
                -self.inventory_rarity_rank(item),
                item.display_name,
            )
        return (
            self.inventory_category(item),
            -self.inventory_rarity_rank(item),
            -self.inventory_power_score(item),
            item.display_name,
        )

    def clamp_inventory_selection(self) -> None:
        count = len(self.player.inventory)
        if count <= 0:
            self.inventory_cursor = 0
            self.inventory_scroll = 0
            return
        self.inventory_cursor = max(0, min(self.inventory_cursor, count - 1))
        self.inventory_scroll = max(0, min(self.inventory_scroll, count - 1))

    def ensure_inventory_cursor_visible(self, visible_rows: int) -> None:
        self.clamp_inventory_selection()
        count = len(self.player.inventory)
        if count <= 0 or visible_rows <= 0:
            self.inventory_scroll = 0
            return
        visible_rows = max(1, min(visible_rows, count))
        if self.inventory_cursor < self.inventory_scroll:
            self.inventory_scroll = self.inventory_cursor
        elif self.inventory_cursor >= self.inventory_scroll + visible_rows:
            self.inventory_scroll = self.inventory_cursor - visible_rows + 1
        max_scroll = max(0, count - visible_rows)
        self.inventory_scroll = max(0, min(self.inventory_scroll, max_scroll))

    def set_inventory_selection(self, index: int, visible_rows: int = 0) -> None:
        if not self.player.inventory:
            self.inventory_cursor = 0
            self.inventory_scroll = 0
            return
        self.inventory_cursor = max(0, min(index, len(self.player.inventory) - 1))
        if visible_rows > 0:
            self.ensure_inventory_cursor_visible(visible_rows)
        else:
            self.clamp_inventory_selection()

    def move_inventory_selection(self, delta: int, visible_rows: int = 0) -> None:
        self.set_inventory_selection(self.inventory_cursor + delta, visible_rows)

    def use_selected_inventory_slot(self) -> None:
        self.clamp_inventory_selection()
        if self.player.inventory:
            self.use_inventory_slot(self.inventory_cursor)

    def drop_selected_inventory_slot(self) -> None:
        self.clamp_inventory_selection()
        if self.player.inventory:
            self.drop_inventory_slot(self.inventory_cursor)

    def sort_inventory(self) -> None:
        self.player.inventory.sort(key=self.inventory_sort_key)
        self.clamp_inventory_selection()
        self.floaters.append(
            FloatingText(
                f"Inventory sorted by {self.inventory_sort_mode}",
                self.player.x,
                self.player.y - 0.4,
                (210, 220, 235),
                ttl=0.9,
            )
        )
        self.save_run()

    def cycle_inventory_sort_mode(self) -> None:
        modes = ("type", "rarity", "power")
        current = (
            modes.index(self.inventory_sort_mode)
            if self.inventory_sort_mode in modes
            else 0
        )
        self.inventory_sort_mode = modes[(current + 1) % len(modes)]
        self.sort_inventory()

    def drop_inventory_slot(self, index: int) -> None:
        if index < 0 or index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        item.x, item.y = self.drop_position_near(self.player.x, self.player.y)
        self.items.append(item)
        self.floaters.append(
            FloatingText(
                f"Dropped {item.display_name}",
                self.player.x,
                self.player.y - 0.4,
                (235, 210, 120),
                ttl=1.0,
            )
        )
        self.play_sfx("pickup")
        self.clamp_inventory_selection()
        self.save_run()

    def use_inventory_slot(self, index: int) -> None:
        if index < 0 or index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        if item.slot == "potion":
            if not self.drink_potion(item):
                self.player.inventory.insert(index, item)
            self.clamp_inventory_selection()
            return
        if item.slot == "mana_potion":
            if not self.drink_mana_potion(item):
                self.player.inventory.insert(index, item)
            self.clamp_inventory_selection()
            return
        if item.slot == "identify":
            self.identify_first_item()
            self.clamp_inventory_selection()
            self.save_run()
            return
        if item.unidentified:
            item.unidentified = False
            self.floaters.append(
                FloatingText(
                    f"Identified {item.name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (160, 220, 255),
                    ttl=1.2,
                )
            )
        old = self.player.equipment.get(item.slot)
        self.player.equipment[item.slot] = item
        if old and len(self.player.inventory) < MAX_INVENTORY:
            self.player.inventory.append(old)
        self.floaters.append(
            FloatingText(
                f"Equipped {item.display_name}",
                self.player.x,
                self.player.y - 0.4,
                (160, 220, 255),
                ttl=1.2,
            )
        )
        self.play_sfx("pickup")
        self.clamp_inventory_selection()
        self.save_run()

    def toggle_quest_info_visibility(self) -> None:
        self.quest_info_visible = not self.quest_info_visible
        label = "Quest info shown" if self.quest_info_visible else "Quest info hidden"
        color = (
            self.story_state.accent
            if self.story_state is not None and self.quest_info_visible
            else (170, 165, 155)
        )
        self.floaters.append(
            FloatingText(label, self.player.x, self.player.y - 0.4, color, ttl=0.9)
        )

    def use_first_potion(self) -> None:
        if self.player.hp >= self.player.max_hp:
            self.floaters.append(
                FloatingText(
                    "Already at full health",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return
        potions = [
            (index, item)
            for index, item in enumerate(self.player.inventory)
            if item.slot == "potion"
        ]
        if potions:
            missing = self.player.max_hp - self.player.hp
            index, item = min(potions, key=lambda entry: abs(entry[1].heal - missing))
            _ = self.player.inventory.pop(index)
            self.drink_potion(item)
            return
        self.floaters.append(
            FloatingText(
                "No potion", self.player.x, self.player.y - 0.4, (235, 210, 120)
            )
        )

    def drink_potion(self, item: Item) -> bool:
        if self.player.hp >= self.player.max_hp:
            self.floaters.append(
                FloatingText(
                    "Already at full health",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return False
        self.run_stats.potions_used += 1
        old_hp = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + item.heal)
        healed = self.player.hp - old_hp
        self.floaters.append(
            FloatingText(
                f"+{healed}", self.player.x, self.player.y - 0.4, (105, 230, 125)
            )
        )
        self.play_sfx("pickup")
        self.save_run()
        return True

    def drink_mana_potion(self, item: Item) -> bool:
        if self.player.mana >= self.player.max_mana:
            self.floaters.append(
                FloatingText(
                    "Already at full mana",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return False
        self.run_stats.potions_used += 1
        old_mana = self.player.mana
        self.player.mana = min(self.player.max_mana, self.player.mana + item.mana)
        restored = int(self.player.mana - old_mana)
        self.floaters.append(
            FloatingText(
                f"+{restored} mana", self.player.x, self.player.y - 0.4, (105, 165, 255)
            )
        )
        self.play_sfx("pickup")
        self.save_run()
        return True

    def identify_first_item(self) -> None:
        unidentified = [item for item in self.player.inventory if item.unidentified]
        if unidentified:
            item = max(
                unidentified,
                key=lambda entry: (
                    self.inventory_rarity_rank(entry),
                    self.inventory_power_score(entry),
                    entry.display_name,
                ),
            )
            item.unidentified = False
            self.floaters.append(
                FloatingText(
                    f"Identified {item.name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (160, 220, 255),
                )
            )
            return
        self.floaters.append(
            FloatingText(
                "Nothing to identify",
                self.player.x,
                self.player.y - 0.4,
                (235, 210, 120),
            )
        )

    def identify_all_items(self) -> int:
        count = 0
        for item in self.player.inventory:
            if item.unidentified:
                item.unidentified = False
                count += 1
        return count

    def world_to_iso(self, x: float, y: float) -> tuple[float, float]:
        return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2

    def camera_iso(self) -> tuple[float, float]:
        return self.world_to_iso(self.player.x, self.player.y)

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        return int(iso_x - cam_x + width * 0.5), int(iso_y - cam_y + height * 0.48)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        iso_x = sx - width * 0.5 + cam_x
        iso_y = sy - height * 0.48 + cam_y
        x = iso_y / TILE_H + iso_x / TILE_W
        y = iso_y / TILE_H - iso_x / TILE_W
        return x, y

    def visible_bounds(self) -> tuple[int, int, int, int]:
        radius = 22
        min_x = max(0, int(self.player.x) - radius)
        max_x = min(MAP_W - 1, int(self.player.x) + radius)
        min_y = max(0, int(self.player.y) - radius)
        max_y = min(MAP_H - 1, int(self.player.y) + radius)
        return min_x, max_x, min_y, max_y


def main() -> None:
    Game().run()
