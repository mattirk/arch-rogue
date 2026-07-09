# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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

import json
from pathlib import Path
from typing import Any

import pygame

from .audio import MusicProfile
from .constants import SCREEN_HEIGHT, SCREEN_WIDTH, UI_SCALE
from .content import (
    DEFAULT_DIFFICULTY_NAME,
    DIFFICULTY_PROFILES,
    HELL_DIFFICULTY_NAME,
    DifficultyProfile,
)
from .input import normalize_gamepad_mapping, serialize_gamepad_mapping


class OptionsMixin:
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
        # Clear the cached font.size() results: the Font objects are replaced, so
        # keys based on id(font) would otherwise collide with the new fonts.
        self._text_size_cache = {}

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

    def default_meta_progress(self) -> dict[str, Any]:
        return {
            "runs_started": 0,
            "clears": 0,
            "best_depth": 0,
            "bosses_defeated": [],
            "themes_seen": [],
            "modifiers_seen": [],
            "legendary_loot_seen": [],
        }

    def normalize_meta_progress(self, data: Any) -> dict[str, Any]:
        progress = self.default_meta_progress()
        if not isinstance(data, dict):
            return progress
        for key in ("runs_started", "clears", "best_depth"):
            try:
                progress[key] = max(0, int(data.get(key, progress[key])))
            except (TypeError, ValueError):
                progress[key] = 0
        for key in (
            "bosses_defeated",
            "themes_seen",
            "modifiers_seen",
            "legendary_loot_seen",
        ):
            values = data.get(key, [])
            if isinstance(values, list):
                progress[key] = sorted({str(value) for value in values if str(value)})[
                    :80
                ]
        return progress

    def options_to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "schema_version": 3,
            "audio_enabled": self.audio_enabled,
            "music_enabled": self.music_enabled,
            "fullscreen": self.fullscreen,
            "ui_scale": self.ui_scale,
            "difficulty": self.difficulty_profile().name,
            "hell_unlocked": self.hell_unlocked,
            "meta_progress": self.meta_progress,
            "run_history": self.run_history[-12:],
            "controller_enabled": getattr(self, "controller_enabled", True),
            "last_controller_guid": getattr(self, "last_controller_guid", ""),
            "gamepad_mapping": serialize_gamepad_mapping(
                normalize_gamepad_mapping(getattr(self, "gamepad_mapping", None))
            ),
            "lighting_enabled": getattr(self, "_lighting_enabled", True),
            "lighting_normal_maps": getattr(self, "_lighting_normal_maps", True),
            "reduced_motion": getattr(self, "_reduced_motion", False),
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
            self.meta_progress = self.normalize_meta_progress(data.get("meta_progress"))
            history = data.get("run_history", [])
            self.run_history = history[-12:] if isinstance(history, list) else []
            self.difficulty_name = self.sanitize_difficulty_name(
                str(data.get("difficulty", DEFAULT_DIFFICULTY_NAME))
            )
            # Schema v3 (milestone 3.9): controller prefs. Missing on older
            # saves -> safe defaults (controller on, no preferred device).
            self.controller_enabled = bool(data.get("controller_enabled", True))
            self.last_controller_guid = str(data.get("last_controller_guid", ""))
            self.gamepad_mapping = normalize_gamepad_mapping(
                data.get("gamepad_mapping")
            )
            # Milestone 3.16 - continuous lighting + accessibility. Missing
            # on older saves falls back to safe native defaults. The web
            # build forces these off in make_game.
            self._lighting_enabled = bool(data.get("lighting_enabled", True))
            self._lighting_normal_maps = bool(data.get("lighting_normal_maps", True))
            self._reduced_motion = bool(data.get("reduced_motion", False))
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
            "controls",
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
