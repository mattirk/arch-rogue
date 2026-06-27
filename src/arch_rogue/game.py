from __future__ import annotations

import math
import random
import re
from pathlib import Path
from typing import Any

import pygame

from . import __version__
from .audio import AudioSystem
from .camera import CameraMixin
from .constants import (
    BOSS_HIT_RADIUS,
    DUNGEON_DEPTH,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    FPS,
    LARGE_ENEMY_HIT_RADIUS,
    PLAYER_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
    PLAYER_PROJECTILE_HIT_RADIUS,
    UI_SCALE,
    WALK_ANIMATION_RATE,
)
from .constants import (
    DARK_LEVEL_LIGHT_RADIUS as DARK_LEVEL_LIGHT_RADIUS,
)
from .constants import (
    MAX_INVENTORY as MAX_INVENTORY,
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
    STORY_LOCATION_MOTIFS,
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
    Enemy,
    FloatingText,
    FloorPlan,
    ImpactEffect,
    Item,
    Player,
    Projectile,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    StoryGuest,
    StoryState,
)
from .models import (
    Room as Room,
)
from .models import (
    Trap as Trap,
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


class Game(
    SaveLoadMixin,
    RenderingMixin,
    OptionsMixin,
    RunFlowMixin,
    PopulationMixin,
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

    def damage_type_color(self, damage_type: str) -> Color:
        return {
            "physical": (255, 210, 120),
            "fire": (255, 132, 74),
            "frost": (126, 206, 242),
            "poison": (126, 214, 92),
            "arcane": (160, 118, 245),
            "holy": (235, 205, 120),
            "shadow": (214, 92, 150),
        }.get(damage_type, (255, 210, 120))

    def weapon_damage_type(self) -> str:
        weapon = self.player.equipment.get("weapon")
        if weapon and weapon.damage_type:
            return weapon.damage_type
        if self.player.class_name == "Arcanist":
            return "arcane"
        if self.player.class_name == "Acolyte":
            return "shadow"
        return "physical"

    def bolt_damage_type(self) -> str:
        weapon = self.player.equipment.get("weapon")
        if weapon and weapon.damage_type in (
            "fire",
            "frost",
            "poison",
            "arcane",
            "shadow",
        ):
            return weapon.damage_type
        return {
            "Warden": "holy",
            "Rogue": "poison" if self.player.has_upgrade("rogue_venom") else "physical",
            "Arcanist": "arcane",
            "Acolyte": "shadow",
            "Ranger": "physical",
        }.get(self.player.class_name, "arcane")

    def nova_damage_type(self) -> str:
        return {
            "Warden": "holy",
            "Rogue": "poison",
            "Arcanist": "frost",
            "Acolyte": "shadow",
            "Ranger": "physical",
        }.get(self.player.class_name, "arcane")

    def equipment_affix_count(self, name: str) -> int:
        return sum(
            1
            for item in self.player.equipment.values()
            if item is not None and name in item.affixes
        )

    def equipment_skill_bonus(self, text: str) -> bool:
        return any(
            item is not None and text in item.skill_bonus
            for item in self.player.equipment.values()
        )

    def equipped_proc_effect(self, effect: str) -> bool:
        return any(
            item is not None and item.proc_effect == effect
            for item in self.player.equipment.values()
        )

    def equipped_unique_effect(self, effect: str) -> bool:
        return any(
            item is not None and item.unique_effect == effect
            for item in self.player.equipment.values()
        )

    def player_status(self, name: str) -> float:
        return float(self.player.status_effects.get(name, 0.0))

    def set_player_status(self, name: str, duration: float) -> None:
        self.player.status_effects[name] = max(
            self.player.status_effects.get(name, 0.0), duration
        )

    def apply_enemy_status(self, enemy: Enemy, status: str, duration: float) -> None:
        if duration <= 0:
            return
        if status == "poisoned" and enemy.resistances.get("poison", 0.0) >= 0.55:
            duration *= 0.55
        enemy.statuses[status] = max(enemy.statuses.get(status, 0.0), duration)
        self.floaters.append(
            FloatingText(
                status.title(),
                enemy.x,
                enemy.y - 0.45,
                self.damage_type_color(
                    "poison"
                    if status == "poisoned"
                    else "frost"
                    if status == "chilled"
                    else "shadow"
                    if status == "bound"
                    else "holy"
                ),
                ttl=0.65,
            )
        )

    def enemy_speed_multiplier(self, enemy: Enemy) -> float:
        multiplier = 1.0
        if enemy.statuses.get("chilled", 0.0) > 0:
            multiplier *= 0.58
        if enemy.statuses.get("snared", 0.0) > 0:
            multiplier *= 0.45
        if enemy.statuses.get("bound", 0.0) > 0:
            multiplier *= 0.62
        return multiplier

    def mitigate_enemy_damage(self, enemy: Enemy, amount: int, damage_type: str) -> int:
        resistance = max(-0.35, min(0.70, enemy.resistances.get(damage_type, 0.0)))
        adjusted = int(round(amount * (1.0 - resistance)))
        if enemy.statuses.get("chilled", 0.0) > 0 and damage_type == "arcane":
            adjusted = int(round(adjusted * 1.18))
        if enemy.statuses.get("snared", 0.0) > 0 and self.player.has_upgrade(
            "ranger_beastmark"
        ):
            adjusted = int(round(adjusted * 1.22))
        return max(1, adjusted)

    def update_enemy_statuses(self, dt: float) -> None:
        for enemy in list(self.enemies):
            if not enemy.statuses:
                continue
            if enemy.statuses.get("poisoned", 0.0) > 0:
                tick = enemy.statuses.get("_poison_tick", 1.0) - dt
                if tick <= 0:
                    enemy.hp -= max(1, int(2 + self.player.level * 0.35))
                    tick += 1.0
                    if enemy.hp <= 0:
                        self.kill_enemy(enemy)
                        continue
                enemy.statuses["_poison_tick"] = tick
            expired: list[str] = []
            for status, ttl in list(enemy.statuses.items()):
                if status.startswith("_"):
                    continue
                ttl -= dt
                if ttl <= 0:
                    expired.append(status)
                else:
                    enemy.statuses[status] = ttl
            if "poisoned" in expired:
                enemy.statuses.pop("_poison_tick", None)
            for status in expired:
                enemy.statuses.pop(status, None)

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
        plan = self.current_floor_plan()
        if plan is not None:
            self.apply_floor_plan_for_current_depth()
            return
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
        if self.equipment_skill_bonus("Melee"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(5, cost)

    def melee_cooldown(self) -> float:
        cooldown = 0.30 if self.player.class_name == "Rogue" else 0.36
        if self.player.has_upgrade("warden_bulwark"):
            cooldown += 0.02
        if self.equipment_skill_bonus("Melee"):
            cooldown -= 0.03
        return max(0.24, cooldown)

    def bolt_mana_cost(self) -> int:
        cost = 7 if self.player.class_name in ("Arcanist", "Ranger") else 10
        if self.player.has_upgrade("arcanist_focus"):
            cost -= 1
        if self.equipment_skill_bonus("Bolt"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(4, cost)

    def bolt_cooldown(self) -> float:
        cooldown = 0.38 if self.player.class_name in ("Arcanist", "Ranger") else 0.48
        if self.equipment_skill_bonus("Bolt"):
            cooldown -= 0.04
        return max(0.28, cooldown)

    def nova_mana_cost(self) -> int:
        cost = 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18
        if self.player.has_upgrade("acolyte_veil"):
            cost -= 2
        if self.equipment_skill_bonus("Nova"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 2
        return max(8, cost)

    def nova_cooldown(self) -> float:
        cooldown = 2.65 if self.player.class_name == "Arcanist" else 3.2
        if self.equipment_skill_bonus("Nova"):
            cooldown -= 0.18
        return max(2.25, cooldown)

    def dash_stamina_cost(self) -> int:
        cost = 12 if self.player.class_name in ("Rogue", "Ranger") else 18
        if self.player.has_upgrade("rogue_smoke"):
            cost -= 2
        if self.equipment_skill_bonus("Dash"):
            cost -= 2
        return max(8, cost)

    def dash_cooldown(self) -> float:
        cooldown = 0.62 if self.player.class_name == "Ranger" else 0.85
        if self.equipment_skill_bonus("Dash tempo"):
            cooldown -= 0.08
        return max(0.48, cooldown)

    def take_player_damage(
        self,
        raw_damage: int,
        source: str = "hit",
        damage_type: str = "physical",
        attacker: Enemy | None = None,
    ) -> int:
        rogue_evade = 0.18 if self.player.has_upgrade("rogue_smoke") else 0.12
        if self.player_status("smoke") > 0:
            rogue_evade += 0.22
        can_evade = source != "trap"
        if (
            can_evade
            and self.player.class_name == "Rogue"
            and self.rng.random() < rogue_evade
        ):
            self.floaters.append(
                FloatingText(
                    "Evaded", self.player.x, self.player.y - 0.2, (170, 220, 170)
                )
            )
            return 0
        armor_bonus = (
            2 if self.player.class_name == "Warden" and source == "melee" else 0
        )
        armor = self.player.equipment.get("armor")
        typed_resist = 0.0
        if armor is not None:
            typed_resist += armor.defense * 0.006
            if armor.damage_type and armor.damage_type == damage_type:
                typed_resist += 0.08
            if "Grounded" in armor.affixes and damage_type == "arcane":
                typed_resist += 0.12
            if "Sealed" in armor.affixes and damage_type in ("shadow", "poison"):
                typed_resist += 0.10
        if self.player_status("aegis") > 0:
            typed_resist += 0.24
        amount = max(1, raw_damage - self.player.armor() - armor_bonus)
        if typed_resist > 0:
            amount = max(1, int(round(amount * (1.0 - min(0.45, typed_resist)))))
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
        if (
            attacker is not None
            and self.player.has_upgrade("warden_riposte")
            and source == "melee"
        ):
            counter = max(2, self.player.level + self.player.armor_bonus)
            self.damage_enemy(
                attacker,
                counter,
                knockback_from=(self.player.facing_x, self.player.facing_y),
                damage_type="holy",
                status_effect="stunned"
                if self.player.has_upgrade("warden_aegis")
                else "",
                status_duration=0.35,
            )
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            amount += 1 if damage_type in ("shadow", "poison") else 0
        self.player.hp -= amount
        if self.player.hp <= 0 and not self.run_stats.cause_of_death:
            self.run_stats.cause_of_death = f"{source} {damage_type} damage"
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
                move_speed = self.player.speed * (
                    0.82 if self.player_status("chilled") > 0 else 1.0
                )
                self.move_actor(
                    self.player,
                    (dx / distance) * move_speed * dt,
                    (dy / distance) * move_speed * dt,
                )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
        self.player.dash_timer = max(0.0, self.player.dash_timer - dt)
        self.player.nova_timer = max(0.0, self.player.nova_timer - dt)
        if self.player_status("poisoned") > 0:
            tick = self.player.status_effects.get("_poison_tick", 1.0) - dt
            if tick <= 0:
                poison_damage = max(1, self.current_depth // 3 + 1)
                self.player.hp -= poison_damage
                if self.player.hp <= 0 and not self.run_stats.cause_of_death:
                    self.run_stats.cause_of_death = "poisoned by lingering venom"
                self.run_stats.damage_taken += poison_damage
                tick += 1.0
                self.floaters.append(
                    FloatingText(
                        f"Poison -{poison_damage}",
                        self.player.x,
                        self.player.y - 0.55,
                        self.damage_type_color("poison"),
                        ttl=0.75,
                    )
                )
            self.player.status_effects["_poison_tick"] = tick
        next_statuses: dict[str, float] = {}
        for status, ttl in self.player.status_effects.items():
            if status.startswith("_"):
                next_statuses[status] = ttl
                continue
            ttl -= dt
            if ttl > 0:
                next_statuses[status] = ttl
        if "poisoned" not in next_statuses:
            next_statuses.pop("_poison_tick", None)
        self.player.status_effects = next_statuses
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
        others: list[Player | Enemy | Shopkeeper]
        if isinstance(actor, Player):
            others = [*self.enemies, *self.shopkeepers]
        else:
            others = [
                self.player,
                *(enemy for enemy in self.enemies if enemy is not actor),
                *self.shopkeepers,
            ]

        for other in others:
            dx = actor.x - other.x
            dy = actor.y - other.y
            distance = math.hypot(dx, dy)
            other_radius = (
                self.actor_hit_radius(other)
                if isinstance(other, (Player, Enemy))
                else 0.34
            )
            min_distance = self.actor_hit_radius(actor) + other_radius
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
            if enemy.statuses.get("stunned", 0.0) > 0:
                enemy.telegraph = "stunned"
                continue
            nx, ny = (dx / distance, dy / distance) if distance > 0.001 else (0.0, 0.0)
            move_speed = enemy.speed * self.enemy_speed_multiplier(enemy)
            if distance > 0.001:
                enemy.facing_x = nx
                enemy.facing_y = ny

            if enemy.kind == "boss":
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                if 2.0 < distance <= 6.0 and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
                elif distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)
            elif enemy.kind == "ranged":
                if 3.5 < distance:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                elif distance < 2.5:
                    self.move_actor(enemy, -nx * move_speed * dt, -ny * move_speed * dt)
                if distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
            else:
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                elif enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)

    def enemy_melee(self, enemy: Enemy) -> None:
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "melee"
        raw = enemy.damage + self.rng.randrange(-2, 3)
        amount = self.take_player_damage(
            raw, source="melee", damage_type=enemy.damage_type, attacker=enemy
        )
        if enemy.damage_type == "poison" and amount > 0:
            self.set_player_status("poisoned", 1.4)
        elif enemy.damage_type == "frost" and amount > 0:
            self.set_player_status("chilled", 0.9)
        self.floaters.append(
            FloatingText(
                f"-{amount}",
                self.player.x,
                self.player.y - 0.2,
                self.damage_type_color(enemy.damage_type),
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
        projectile_color = self.damage_type_color(enemy.damage_type)
        if enemy.elite_modifier:
            projectile_color = self.mix(projectile_color, (245, 100, 235), 0.35)
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
                damage_type=enemy.damage_type,
                status_effect="chilled" if enemy.damage_type == "frost" else "",
                status_duration=0.9,
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
                        damage_type=projectile.damage_type,
                        status_effect=projectile.status_effect,
                        status_duration=projectile.status_duration,
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
                        projectile.damage,
                        source="projectile",
                        damage_type=projectile.damage_type,
                    )
                    if projectile.status_effect == "chilled" and amount > 0:
                        self.set_player_status("chilled", projectile.status_duration)
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
                damage_type = self.weapon_damage_type()
                status_effect = ""
                status_duration = 0.0
                if self.equipment_skill_bonus("Melee"):
                    damage += 2
                if index > 0:
                    damage = max(1, int(damage * 0.62))
                crit_chance = (
                    0.30 if self.player.has_upgrade("rogue_precision") else 0.22
                )
                rogue_crit = (
                    self.player.class_name == "Rogue"
                    and self.rng.random() < crit_chance
                )
                if rogue_crit:
                    damage = int(
                        damage
                        * (1.95 if self.player.has_upgrade("rogue_precision") else 1.75)
                    )
                    status_effect = "poisoned"
                    status_duration = (
                        2.2 if self.player.has_upgrade("rogue_venom") else 1.2
                    )
                    self.floaters.append(
                        FloatingText(
                            "Critical", enemy.x, enemy.y - 0.45, (255, 225, 120)
                        )
                    )
                if self.player.class_name == "Warden":
                    enemy.attack_timer = max(enemy.attack_timer, 0.35)
                    if self.player.has_upgrade("warden_aegis"):
                        damage_type = "holy"
                        status_effect = "stunned"
                        status_duration = 0.35
                elif self.player.class_name == "Arcanist" and self.player.has_upgrade(
                    "arcanist_permafrost"
                ):
                    status_effect = "chilled"
                    status_duration = 1.0
                elif self.player.class_name == "Acolyte" and self.player.has_upgrade(
                    "acolyte_gravebind"
                ):
                    status_effect = "bound"
                    status_duration = 1.1
                elif self.player.class_name == "Ranger" and self.player.has_upgrade(
                    "ranger_beastmark"
                ):
                    status_effect = "snared"
                    status_duration = 1.15
                damage = self.apply_story_player_damage(damage)
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=(self.player.facing_x, self.player.facing_y),
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
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
        damage_type = self.bolt_damage_type()
        damage = 14 + self.player.level * 2 + self.player.spell_bonus
        if self.equipment_skill_bonus("Bolt"):
            damage += 2
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
        if self.equipment_skill_bonus("Bolt") and len(angles) < 5:
            angles = sorted({*angles, -0.18, 0.18})
        status_effect = ""
        status_duration = 0.0
        if damage_type == "poison" or self.player.has_upgrade("rogue_venom"):
            status_effect = "poisoned"
            status_duration = 2.0
        elif damage_type == "frost" or self.player.has_upgrade("arcanist_permafrost"):
            status_effect = "chilled"
            status_duration = 1.4
        elif self.player.has_upgrade("acolyte_gravebind"):
            status_effect = "bound"
            status_duration = 1.2
        elif self.player.has_upgrade("ranger_snare"):
            status_effect = "snared"
            status_duration = 1.1
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
                    self.damage_type_color(damage_type),
                    ttl=1.55 if self.player.has_upgrade("arcanist_splinter") else 1.4,
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
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
            if self.equipment_skill_bonus("Nova"):
                radius += 0.25
            if distance <= radius:
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                damage_type = self.nova_damage_type()
                status_effect = ""
                status_duration = 0.0
                if self.equipment_skill_bonus("Nova"):
                    damage += 2
                if self.player.class_name == "Warden":
                    status_effect = "stunned"
                    status_duration = (
                        0.35 if self.player.has_upgrade("warden_aegis") else 0.2
                    )
                    enemy.attack_timer = max(enemy.attack_timer, 0.45)
                elif self.player.class_name == "Rogue":
                    status_effect = "poisoned"
                    status_duration = (
                        2.4 if self.player.has_upgrade("rogue_venom") else 1.4
                    )
                    self.set_player_status("smoke", 0.65)
                elif self.player.class_name == "Arcanist":
                    status_effect = "chilled"
                    status_duration = (
                        1.9 if self.player.has_upgrade("arcanist_permafrost") else 1.2
                    )
                elif self.player.class_name == "Ranger":
                    snare_time = (
                        1.25 if self.player.has_upgrade("ranger_snare") else 0.8
                    )
                    enemy.attack_timer = max(enemy.attack_timer, snare_time)
                    status_effect = "snared"
                    status_duration = snare_time
                if self.player.class_name == "Acolyte":
                    leech = 5 if self.player.has_upgrade("acolyte_sanguine") else 3
                    self.player.hp = min(self.player.max_hp, self.player.hp + leech)
                    if self.player.has_upgrade("acolyte_gravebind"):
                        status_effect = "bound"
                        status_duration = 1.6
                damage = self.apply_story_player_damage(damage, spell=True)
                direction = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (self.player.facing_x, self.player.facing_y)
                )
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=direction,
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
                )
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
        if self.equipment_skill_bonus("Dash"):
            steps += 1
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
        if self.player.class_name == "Rogue" and self.player.has_upgrade("rogue_smoke"):
            self.set_player_status("smoke", 0.9)
        if self.player.class_name == "Warden" and (
            self.player.has_upgrade("warden_aegis")
            or self.equipment_skill_bonus("Dash guard")
        ):
            self.set_player_status("aegis", 0.85)
        if self.player.class_name == "Ranger" and self.player.has_upgrade(
            "ranger_beastmark"
        ):
            self.player.stamina = min(self.player.max_stamina, self.player.stamina + 8)
            self.player.bolt_timer = min(self.player.bolt_timer, 0.12)
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
        self,
        enemy: Enemy,
        amount: int,
        knockback_from: tuple[float, float],
        damage_type: str = "physical",
        status_effect: str = "",
        status_duration: float = 0.0,
    ) -> None:
        amount = self.mitigate_enemy_damage(enemy, amount, damage_type)
        proc_damage = 0
        weapon = self.player.equipment.get("weapon")
        if (
            self.equipped_unique_effect("embers on hit")
            or self.equipped_proc_effect("ignite")
            or (weapon is not None and weapon.proc_effect == "ignite")
        ) and damage_type != "fire":
            proc_damage += max(1, self.player.level // 2 + 2)
            self.apply_enemy_status(enemy, "burning", 1.1)
        if (
            self.equipped_unique_effect("chill on hit")
            or self.equipped_proc_effect("chill")
            or status_effect == "chilled"
        ):
            self.apply_enemy_status(enemy, "chilled", max(status_duration, 1.0))
        if self.equipped_proc_effect("lifesteal"):
            healed = min(
                self.player.max_hp - self.player.hp, 2 + self.player.level // 3
            )
            if healed > 0:
                self.player.hp += healed
                self.floaters.append(
                    FloatingText(
                        f"+{healed}",
                        self.player.x,
                        self.player.y - 0.45,
                        (214, 92, 150),
                    )
                )
        if status_effect and status_effect != "chilled":
            self.apply_enemy_status(enemy, status_effect, status_duration)
        if enemy.statuses.get("burning", 0.0) > 0 and damage_type == "fire":
            proc_damage += max(1, self.player.level // 3 + 1)
        total = max(1, amount + proc_damage)
        enemy.hp -= total
        self.enemy_hit_flashes[id(enemy)] = 0.22 if enemy.kind != "boss" else 0.32
        hit_color = (
            self.theme.accent
            if enemy.kind == "boss"
            else self.damage_type_color(damage_type)
        )
        self.floaters.append(
            FloatingText(f"-{total}", enemy.x, enemy.y - 0.2, hit_color)
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
            if enemy.name not in self.run_stats.defeated_bosses:
                self.run_stats.defeated_bosses.append(enemy.name)
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            unique = self._make_unique(drop_x, drop_y)
            self.items.append(unique)
            self.record_notable_loot(unique)
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
            if enemy.role in ("floor_boss", "challenge_boss"):
                if enemy.name not in self.run_stats.defeated_bosses:
                    self.run_stats.defeated_bosses.append(enemy.name)
                plan = self.current_floor_plan()
                if plan is not None and plan.encounter_key == "challenge_room":
                    self.run_stats.challenge_rooms_cleared += 1
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            rare = self._make_equipment(
                self.rng.choice(("weapon", "armor")), "Rare", drop_x, drop_y
            )
            self.items.append(rare)
            self.record_notable_loot(rare)
        elif enemy.elite_modifier:
            self.run_stats.elites_killed += 1
        xp_gain = max(
            1, int(enemy.xp * (1.0 + self.story_effect_value("xp_bonus", 0.0, 0.35)))
        )
        if (
            self.player.class_name == "Acolyte"
            and self.player.has_upgrade("acolyte_gravebind")
            and enemy.statuses.get("bound", 0.0) > 0
        ):
            echo_heal = min(
                self.player.max_hp - self.player.hp, 4 + self.current_depth // 2
            )
            if echo_heal > 0:
                self.player.hp += echo_heal
                self.player.mana = min(self.player.max_mana, self.player.mana + 2)
                self.floaters.append(
                    FloatingText(
                        f"Grave echo +{echo_heal}",
                        self.player.x,
                        self.player.y - 0.5,
                        self.damage_type_color("shadow"),
                        ttl=0.85,
                    )
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
            loot = self._make_loot(drop_x, drop_y)
            self.items.append(loot)
            self.record_notable_loot(loot)
        gold = self.rng.randrange(4, 11) + self.current_depth * 2
        if enemy.elite_modifier:
            gold += 8
        if enemy.kind in ("boss", "miniboss"):
            gold += 18
        self.player.gold += gold
        self.floaters.append(
            FloatingText(f"+{gold} gold", enemy.x, enemy.y - 0.55, (225, 190, 92))
        )
        self.save_run()


def main() -> None:
    Game().run()
