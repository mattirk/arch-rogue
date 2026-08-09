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

import io
import json
import logging
import math
from collections import OrderedDict
from functools import lru_cache
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from collections.abc import Iterable, Iterator
from typing import Any, Callable, Generic, TypeVar

import pygame

from ..constants import (
    GRAPHICS_TIER_DEFAULT,
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_LEGACY,
    GRAPHICS_TIER_MODERN,
    LIGHT_SHADE_DOWNSAMPLE_LONG,
    TILE_W,
    WORLD_SCALE,
    normalize_graphics_tier,
)
from ..mobile import optimize_immutable_alpha_surface
from ..models import Color
from .procedural import PixelSpriteAtlas

LOGGER = logging.getLogger(__name__)
DIRECTIONS = (
    "south",
    "south-east",
    "east",
    "north-east",
    "north",
    "north-west",
    "west",
    "south-west",
)
_ACTION_STATES = frozenset(
    ("attack", "cast", "hit", "dash", "pet", "act", "die", "dead")
)
_SUPPORTED_ACTOR_STATES = frozenset(
    ("idle", "walk", "dance", "attack", "cast", "pet", "act", "die", "dead")
)
GOLD_STACK_ASSET_KEYS = (
    "gold_stack",
    "gold_stack_02",
    "gold_stack_03",
    "gold_stack_04",
    "gold_stack_05",
)
# 4.2.x theater redesign: cutscene stage prop kinds -> authored prop sprites.
STAGE_PROP_ASSET_KEYS = {
    "pillar": "stage_pillar",
    "altar": "stage_altar",
    "lectern": "stage_lectern",
    "candelabra": "stage_candelabra",
    "banner": "stage_banner",
    "mirror": "lossless_memory_mirror",
    "chimes": "lossless_memory_chimes",
    "brazier": "lossless_soul_brazier",
    "reliquary": "lossless_memory_reliquary",
}
# 4.8.6 soul hall furnishings: world-prop keys by furnishing anchor name.
# These are dedicated tile-fitting isometric versions; the flat portrait art
# (lossless_memory_* / lossless_soul_brazier) is reserved for the cutscene
# stage via STAGE_PROP_ASSET_KEYS above.
LOSSLESS_SOUL_PROP_ASSET_KEYS = {
    "soul_mirror": "lossless_room_mirror",
    "soul_chimes": "lossless_room_chimes",
    "soul_brazier": "lossless_room_brazier",
    "soul_reliquary": "lossless_room_reliquary",
}
# Special wall faces are named for their screen side, while PixelLab rotations
# use the same screen-space compass directions as actor sprites. The +y
# (left) face points south-west; the +x (right) face points south-east.
BAR_WALL_SCONCE_DIRECTION_BY_FACE = {
    "left": "south-west",
    "right": "south-east",
}

_K = TypeVar("_K")
_V = TypeVar("_V")


@dataclass(frozen=True, slots=True)
class ResolvedSpriteFrame:
    """A cached sprite surface and its world-contact anchor."""

    surface: pygame.Surface
    anchor: tuple[int, int]
    source: str
    key: tuple[object, ...]

    @property
    def is_asset(self) -> bool:
        return self.source == "asset"


class _LruCache(Generic[_K, _V]):
    def __init__(
        self,
        maximum: int,
        *,
        maximum_weight: int | None = None,
        weigh: Callable[[_V], int] | None = None,
    ) -> None:
        self.maximum = max(1, maximum)
        self.maximum_weight = (
            max(1, int(maximum_weight))
            if maximum_weight is not None
            else None
        )
        self._weigh = weigh
        self.weight = 0
        self._values: OrderedDict[_K, _V] = OrderedDict()

    def get(self, key: _K) -> _V | None:
        value = self._values.get(key)
        if value is not None:
            self._values.move_to_end(key)
        return value

    def put(self, key: _K, value: _V) -> _V:
        previous = self._values.pop(key, None)
        if previous is not None:
            self.weight -= self._value_weight(previous)
        self._values[key] = value
        self.weight += self._value_weight(value)
        self._values.move_to_end(key)
        while len(self._values) > 1 and (
            len(self._values) > self.maximum
            or (
                self.maximum_weight is not None
                and self.weight > self.maximum_weight
            )
        ):
            _old_key, old_value = self._values.popitem(last=False)
            self.weight -= self._value_weight(old_value)
        return value

    def clear(self) -> None:
        self._values.clear()
        self.weight = 0

    def __len__(self) -> int:
        return len(self._values)

    def _value_weight(self, value: _V) -> int:
        if self._weigh is None:
            return 0
        return max(0, int(self._weigh(value)))


class AssetSpriteLibrary:
    """Validated, lazy loader for packaged authored sprite resources.

    Image decode, scaling, tinting, and special-room decoration are all cached.
    A bad or missing individual resource resolves to ``None`` so the facade can
    fall back to procedural art without disabling the rest of the asset set.
    """

    MANIFEST_NAME = "manifest.json"
    MODERN_WORLD_MANIFEST_NAME = "world_modern.json"
    # Count bounds alone are unsafe now that one logical tile can resolve from
    # ~330 px to ~525 px.  This cap includes pixel storage for every retained
    # bucketed world canvas and prevents a pinch sweep from retaining hundreds
    # of MiB even though the entry count is still below 192.
    WORLD_CACHE_BYTE_BUDGET = 64 * 1024 * 1024
    # The historical mobile-safe source/frame caps (48 decoded sheets, 320
    # normalized frames) are smaller than a depth-10 desktop crowd's working
    # set (~350+ resolution keys across enemy types, directions, and animation
    # frames). Below-working-set LRUs thrash: steady combat frames were
    # re-decoding PNGs and re-normalizing frames every frame, which is
    # especially expensive on Windows (file I/O + antivirus scanning). Desktop
    # therefore trades bounded memory for zero steady-state decode work; the
    # byte budgets keep a pathological asset set from retaining unbounded RAM.
    CACHE_PROFILES: dict[str, dict[str, int | None]] = {
        "mobile": {
            "source_entries": 48,
            "source_bytes": None,
            "frame_entries": 320,
            "frame_bytes": None,
            "resolved_entries": 512,
        },
        "desktop": {
            # 4.11.0: 384 entries thrashed — a populated floor's actor working
            # set (player clips + 20-30 enemies x clips x directions + NPCs)
            # exceeds it, so sources evicted and reloaded from disk on gameplay
            # frames all fight long (hitch logs: decoded pinned at 384 with
            # loads:+36..76 per report window). The byte budget below is the
            # real memory guard; the entry cap just needs to stay above a
            # floor's working set.
            "source_entries": 2560,
            # 320MB: a dense floor's full actor roster measures ~1300 sources
            # / ~230MB decoded; the previous 192MB evicted the earliest-warmed
            # third of the prewarm again before the fight started.
            "source_bytes": 320 * 1024 * 1024,
            "frame_entries": 4096,
            "frame_bytes": 128 * 1024 * 1024,
            "resolved_entries": 4096,
        },
    }

    def __init__(
        self,
        asset_root: Path | Traversable | None = None,
        *,
        world_graphics_tier: str = GRAPHICS_TIER_HD,
        cache_profile: str = "desktop",
    ) -> None:
        self._bundled_assets = asset_root is None
        if asset_root is None:
            asset_root = resources.files("arch_rogue.assets").joinpath("sprites")
        self.root: Path | Traversable = asset_root
        self.manifest: dict[str, Any] = {}
        self._world_manifests: dict[str, dict[str, Any]] = {}
        selected_world_tier = normalize_graphics_tier(
            world_graphics_tier,
            default=GRAPHICS_TIER_HD,
        )
        self.world_graphics_tier = (
            GRAPHICS_TIER_MODERN
            if selected_world_tier == GRAPHICS_TIER_MODERN
            else GRAPHICS_TIER_HD
        )
        self.available = False
        self.load_error = ""
        self.modern_world_load_error = ""
        self.modern_world_available = False
        self.source_load_count = 0
        self.frame_build_count = 0
        profile = self.CACHE_PROFILES.get(
            cache_profile, self.CACHE_PROFILES["desktop"]
        )
        self.cache_profile = (
            cache_profile if cache_profile in self.CACHE_PROFILES else "desktop"
        )

        def surface_bytes(surface: pygame.Surface) -> int:
            return surface.get_width() * surface.get_height() * surface.get_bytesize()

        self._source_cache: _LruCache[str, pygame.Surface] = _LruCache(
            int(profile["source_entries"] or 48),
            maximum_weight=profile["source_bytes"],
            weigh=surface_bytes,
        )
        self._frame_cache: _LruCache[tuple[object, ...], ResolvedSpriteFrame] = (
            _LruCache(
                int(profile["frame_entries"] or 320),
                maximum_weight=profile["frame_bytes"],
                weigh=lambda frame: surface_bytes(frame.surface),
            )
        )
        self._world_cache: _LruCache[
            tuple[object, ...], tuple[pygame.Surface, int, int]
        ] = _LruCache(
            192,
            maximum_weight=self.WORLD_CACHE_BYTE_BUDGET,
            weigh=lambda resolved: (
                resolved[0].get_width()
                * resolved[0].get_height()
                * resolved[0].get_bytesize()
            ),
        )
        self._resolved_actor_cache: _LruCache[
            tuple[object, ...], tuple[object, ...]
        ] = _LruCache(int(profile["resolved_entries"] or 512))
        self._missing_resources: set[str] = set()
        self._actor_aliases: dict[str, str] = {}
        self._actor_slug_cache: dict[tuple[str, str], str | None] = {}
        self._item_aliases: dict[str, str] = {}
        self._prop_aliases: dict[str, str] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        try:
            data = json.loads(self._resource(self.MANIFEST_NAME).read_text(encoding="utf-8"))
            self._validate_manifest(data)
        except (
            AttributeError,
            IndexError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            self.load_error = str(exc)
            return
        self.manifest = data
        self._world_manifests[GRAPHICS_TIER_HD] = data["world"]
        try:
            modern_data = json.loads(
                self._resource(self.MODERN_WORLD_MANIFEST_NAME).read_text(
                    encoding="utf-8"
                )
            )
            if (
                not isinstance(modern_data, dict)
                or modern_data.get("format_version") != 1
                or not isinstance(modern_data.get("world"), dict)
            ):
                raise ValueError("unsupported Modern world asset manifest")
            # Reuse the canonical entry/path validation without duplicating
            # the actor/item/prop rules. Empty maps are valid here because the
            # companion manifest intentionally contains only world resources.
            self._validate_manifest(
                {
                    "format_version": 1,
                    "actors": {},
                    "items": {},
                    "props": {},
                    "world": modern_data["world"],
                }
            )
            self._world_manifests[GRAPHICS_TIER_MODERN] = modern_data["world"]
            self.modern_world_available = True
        except FileNotFoundError as exc:
            # Third-party/test manifests written before graphics tiers remain
            # valid; their main world map serves both authored tiers.
            if self._bundled_assets:
                self.modern_world_load_error = str(exc)
                LOGGER.warning(
                    "Bundled Modern world asset manifest is missing: %s", exc
                )
        except (
            AttributeError,
            IndexError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            self.modern_world_load_error = str(exc)
            LOGGER.warning(
                "Modern world asset manifest could not be loaded: %s", exc
            )
        for slug, entry in data["actors"].items():
            self._actor_aliases[str(slug).casefold()] = str(slug)
            self._actor_aliases[str(entry.get("name", slug)).casefold()] = str(slug)
            for alias in entry.get("aliases", []):
                self._actor_aliases[str(alias).casefold()] = str(slug)
        for key, entry in data["items"].items():
            self._item_aliases[str(key).casefold()] = str(key)
            for alias in entry.get("aliases", []):
                self._item_aliases[str(alias).casefold()] = str(key)
        for key, entry in data["props"].items():
            self._prop_aliases[str(key).casefold()] = str(key)
            for alias in entry.get("aliases", []):
                self._prop_aliases[str(alias).casefold()] = str(key)
        self.available = True

    def _validate_manifest(self, data: object) -> None:
        if not isinstance(data, dict) or data.get("format_version") != 1:
            raise ValueError("unsupported asset sprite manifest")
        for category in ("actors", "items", "props", "world"):
            if not isinstance(data.get(category), dict):
                raise ValueError(f"asset sprite manifest has no {category} map")

        def validate_anchor(entry: dict[str, Any], label: str) -> None:
            if "source_anchor" not in entry:
                return
            anchor = entry["source_anchor"]
            if (
                not isinstance(anchor, (list, tuple))
                or len(anchor) != 2
                or not all(isinstance(value, (int, float)) for value in anchor)
                or not all(math.isfinite(float(value)) for value in anchor)
            ):
                raise ValueError(f"invalid {label} source anchor")

        def validate_scale(entry: dict[str, Any], field: str, label: str) -> None:
            if field not in entry:
                return
            value = entry[field]
            if (
                not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(f"invalid {label} {field}")

        def validate_aliases(entry: dict[str, Any], label: str) -> None:
            aliases = entry.get("aliases", [])
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                raise ValueError(f"invalid {label} alias list")

        for entry in data["actors"].values():
            if not isinstance(entry, dict):
                raise ValueError("invalid actor asset entry")
            for field in ("source_anchor", "reference_height", "target_height", "rotations"):
                if field not in entry:
                    raise ValueError(f"actor asset entry has no {field}")
            validate_anchor(entry, "actor")
            validate_aliases(entry, "actor")
            validate_scale(entry, "reference_height", "actor")
            validate_scale(entry, "target_height", "actor")
            rotations = entry["rotations"]
            if not isinstance(rotations, dict):
                raise ValueError("invalid actor rotation map")
            missing_rotations = set(DIRECTIONS).difference(rotations)
            if missing_rotations:
                raise ValueError(
                    f"actor asset is missing rotations: {sorted(missing_rotations)}"
                )
            for path in rotations.values():
                self._validated_path(str(path))
            clips = entry.get("clips", {})
            if not isinstance(clips, dict):
                raise ValueError("invalid actor clip map")
            for clip in clips.values():
                if not isinstance(clip, dict) or not isinstance(clip.get("directions"), dict):
                    raise ValueError("invalid actor clip")
                fps = clip.get("fps", 6.0)
                if (
                    not isinstance(fps, (int, float))
                    or not math.isfinite(float(fps))
                    or float(fps) <= 0.0
                ):
                    raise ValueError("invalid actor clip frame rate")
                if "loop" in clip and not isinstance(clip["loop"], bool):
                    raise ValueError("invalid actor clip loop flag")
                clip_directions = clip["directions"]
                if not clip_directions:
                    raise ValueError("actor clip has no directions")
                unknown_directions = set(clip_directions).difference(DIRECTIONS)
                if unknown_directions:
                    raise ValueError(
                        f"actor clip has invalid directions: {sorted(unknown_directions)}"
                    )
                for frame_paths in clip_directions.values():
                    if not isinstance(frame_paths, list) or not frame_paths:
                        raise ValueError("invalid actor frame list")
                    for path in frame_paths:
                        self._validated_path(str(path))

        def validate_path_list(
            entry: dict[str, Any], field: str, label: str
        ) -> None:
            paths = entry.get(field)
            if paths is None:
                return
            if not isinstance(paths, list) or not paths:
                raise ValueError(f"invalid {label} {field} list")
            for path in paths:
                self._validated_path(str(path))

        def validate_animation(entry: dict[str, Any], label: str) -> None:
            frames = entry.get("frames")
            overlay_frames = entry.get("overlay_frames")
            if frames is not None and overlay_frames is not None:
                raise ValueError(
                    f"invalid {label} animation: frames and overlay_frames conflict"
                )
            if frames is None and overlay_frames is None:
                return
            fps = entry.get("fps", 6.0)
            if (
                not isinstance(fps, (int, float))
                or not math.isfinite(float(fps))
                or float(fps) <= 0.0
            ):
                raise ValueError(f"invalid {label} animation frame rate")
            if "ping_pong" in entry and not isinstance(entry["ping_pong"], bool):
                raise ValueError(f"invalid {label} animation ping-pong flag")

        for category in ("items", "props", "world"):
            label = category.removesuffix("s")
            for entry in data[category].values():
                if not isinstance(entry, dict):
                    raise ValueError(f"invalid {label} asset entry")
                self._validated_path(str(entry.get("path", "")))
                validate_anchor(entry, label)
                validate_aliases(entry, label)
                validate_scale(entry, "reference_height", label)
                validate_scale(entry, "target_height", label)
                validate_path_list(entry, "frames", label)
                validate_path_list(entry, "variants", label)
                validate_path_list(entry, "overlay_frames", label)
                validate_animation(entry, label)
        for entry in data["world"].values():
            validate_scale(entry, "reference_width", "world")
            tint_strength = entry.get("tint_strength", 0.5)
            if not isinstance(tint_strength, (int, float)) or not math.isfinite(
                float(tint_strength)
            ):
                raise ValueError("invalid world tint strength")

    def _validated_path(self, value: str) -> PurePosixPath:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or path.suffix.casefold() != ".png"
        ):
            raise ValueError(f"unsafe asset sprite path: {value!r}")
        return path

    def _resource(self, value: str):
        metadata_names = {
            self.MANIFEST_NAME,
            self.MODERN_WORLD_MANIFEST_NAME,
        }
        path = (
            PurePosixPath(value)
            if value in metadata_names
            else self._validated_path(value)
        )
        resource = self.root
        for part in path.parts:
            resource = resource.joinpath(part)
        return resource

    def _warn_missing_once(self, path: str, error: Exception) -> None:
        if path in self._missing_resources:
            return
        self._missing_resources.add(path)
        LOGGER.warning("Asset sprite %s could not be loaded: %s", path, error)

    def _source_surface(self, path: str) -> pygame.Surface | None:
        cached = self._source_cache.get(path)
        if cached is not None:
            return cached
        if path in self._missing_resources:
            return None
        try:
            data = self._resource(path).read_bytes()
            surface = pygame.image.load(io.BytesIO(data), PurePosixPath(path).name)
            try:
                surface = surface.convert_alpha()
            except pygame.error:
                surface = surface.copy()
            self.source_load_count += 1
        except (OSError, RuntimeError, ValueError, pygame.error) as exc:
            self._warn_missing_once(path, exc)
            return None
        return self._source_cache.put(path, surface)

    @staticmethod
    def _normalized_frame_cache_key(
        path: str, entry: dict[str, Any]
    ) -> tuple[object, ...]:
        source_anchor = entry.get("source_anchor", (0.0, 0.0))
        reference_height = max(1.0, float(entry.get("reference_height", 1.0)))
        target_height = max(1.0, float(entry.get("target_height", reference_height)))
        return (
            path,
            round(float(source_anchor[0]), 3),
            round(float(source_anchor[1]), 3),
            round(reference_height, 3),
            round(target_height, 3),
        )

    def _normalized_frame(
        self,
        path: str,
        entry: dict[str, Any],
        identity: tuple[object, ...],
        cache_key: tuple[object, ...] | None = None,
    ) -> ResolvedSpriteFrame | None:
        source_anchor = entry.get("source_anchor", (0.0, 0.0))
        reference_height = max(1.0, float(entry.get("reference_height", 1.0)))
        target_height = max(1.0, float(entry.get("target_height", reference_height)))
        if cache_key is None:
            cache_key = self._normalized_frame_cache_key(path, entry)
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached
        source = self._source_surface(path)
        if source is None:
            return None
        bounds = source.get_bounding_rect(min_alpha=1)
        if bounds.width <= 0 or bounds.height <= 0:
            return None

        anchor_x = float(source_anchor[0])
        anchor_y = float(source_anchor[1])
        padding = 2
        left = max(0, min(bounds.left - padding, math.floor(anchor_x) - 1))
        right = min(
            source.get_width(), max(bounds.right + padding, math.ceil(anchor_x) + 1)
        )
        top = max(0, bounds.top - padding)
        bottom = min(
            source.get_height(), max(bounds.bottom + padding, math.ceil(anchor_y))
        )
        crop_rect = pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))
        cropped = source.subsurface(crop_rect).copy()
        scale = target_height / reference_height
        output_size = (
            max(1, round(cropped.get_width() * scale)),
            max(1, round(cropped.get_height() * scale)),
        )
        if output_size != cropped.get_size():
            cropped = pygame.transform.scale(cropped, output_size)
        try:
            cropped = cropped.convert_alpha()
        except pygame.error:
            pass
        cropped = optimize_immutable_alpha_surface(cropped)
        frame = ResolvedSpriteFrame(
            cropped,
            (
                round((anchor_x - crop_rect.left) * scale),
                round((anchor_y - crop_rect.top) * scale),
            ),
            "asset",
            identity,
        )
        self.frame_build_count += 1
        return self._frame_cache.put(cache_key, frame)

    def _actor_slug(self, name: str, kind: str = "") -> str | None:
        folded = str(name).strip().casefold()
        cache_key = (folded, kind)
        if cache_key in self._actor_slug_cache:
            return self._actor_slug_cache[cache_key]

        result = self._actor_aliases.get(folded)
        actors = self.manifest.get("actors", {})
        if result is None:
            candidates: list[tuple[int, str]] = []
            for slug, entry in actors.items():
                if entry.get("category") not in ("enemy", "boss"):
                    continue
                aliases = [entry.get("name", slug), *entry.get("aliases", [])]
                for alias in aliases:
                    alias_folded = str(alias).casefold()
                    if alias_folded and alias_folded in folded:
                        candidates.append((len(alias_folded), str(slug)))
            if candidates:
                result = max(candidates)[1]
            elif kind == "boss" or "gate tyrant" in folded:
                result = "gate_tyrant" if "gate_tyrant" in actors else None

        if len(self._actor_slug_cache) >= 512:
            self._actor_slug_cache.clear()
        self._actor_slug_cache[cache_key] = result
        return result

    def resolve_actor(
        self,
        name: str,
        state: str,
        direction: str,
        clip_time: float,
        *,
        kind: str = "",
        clip_progress: float | None = None,
        loop_progress: float | None = None,
        native: bool = False,
    ) -> ResolvedSpriteFrame | None:
        if not self.available:
            return None
        slug = self._actor_slug(name, kind)
        if slug is None:
            return None
        entry = self.manifest["actors"].get(slug)
        if not isinstance(entry, dict):
            return None
        if native:
            # Native presentation: keep the authored source pixels 1:1 by
            # collapsing the target scale onto the reference height. The
            # cache keys embed target/reference so native frames never
            # collide with the world-scaled ones.
            entry = dict(entry)
            entry["target_height"] = entry.get("reference_height", 1.0)
            slug = f"{slug}@native"
        if direction not in DIRECTIONS:
            direction = "south"

        requested_state = state if state in _SUPPORTED_ACTOR_STATES else ""
        if state == "dash":
            requested_state = "walk"
        clips = entry.get("clips", {})
        clip_name = requested_state if requested_state in clips else "idle"
        clip = clips.get(clip_name)
        if isinstance(clip, dict):
            by_direction = clip.get("directions", {})
            frame_paths = by_direction.get(direction)
            used_direction = direction
            if (
                not frame_paths
                and by_direction
                and clip_name in ("die", "dead", "act")
            ):
                # Death and flourish ("act") clips are authored
                # single-direction by design: play them for every facing
                # rather than dropping to a static rotation frame. Other
                # partial clips keep the matching rotation fallback so e.g.
                # an east walk never shows the south-facing frames.
                fallback = "south" if "south" in by_direction else next(
                    iter(by_direction)
                )
                frame_paths = by_direction.get(fallback)
                used_direction = fallback
            if frame_paths:
                fps = max(0.1, float(clip.get("fps", 6.0)))
                looping = bool(clip.get("loop", True))
                if looping and loop_progress is not None:
                    progress = float(loop_progress) % 1.0
                    frame_number = min(
                        len(frame_paths) - 1,
                        int(progress * len(frame_paths)),
                    )
                elif not looping and clip_progress is not None:
                    progress = max(0.0, min(1.0, float(clip_progress)))
                    frame_number = min(
                        len(frame_paths) - 1,
                        int(progress * len(frame_paths)),
                    )
                else:
                    frame_number = max(0, int(max(0.0, clip_time) * fps))
                    if looping:
                        frame_number %= len(frame_paths)
                    else:
                        frame_number = min(len(frame_paths) - 1, frame_number)
                path = str(frame_paths[frame_number])
                identity = ("actor", slug, clip_name, used_direction, frame_number)
                frame_cache_key = self._resolved_actor_cache.get(identity)
                if frame_cache_key is not None:
                    cached = self._frame_cache.get(frame_cache_key)
                    if cached is not None:
                        return cached
                frame_cache_key = self._normalized_frame_cache_key(path, entry)
                frame = self._normalized_frame(
                    path,
                    entry,
                    identity,
                    cache_key=frame_cache_key,
                )
                if frame is not None:
                    self._resolved_actor_cache.put(identity, frame_cache_key)
                    return frame

        rotations = entry.get("rotations", {})
        path = rotations.get(direction) or rotations.get("south")
        if path is None and rotations:
            direction, path = next(iter(rotations.items()))
        if path is None:
            return None
        identity = ("actor", slug, "rotation", direction, 0)
        frame_cache_key = self._resolved_actor_cache.get(identity)
        if frame_cache_key is not None:
            cached = self._frame_cache.get(frame_cache_key)
            if cached is not None:
                return cached
        path = str(path)
        frame_cache_key = self._normalized_frame_cache_key(path, entry)
        frame = self._normalized_frame(
            path,
            entry,
            identity,
            cache_key=frame_cache_key,
        )
        if frame is not None:
            self._resolved_actor_cache.put(identity, frame_cache_key)
        return frame

    @staticmethod
    def _actor_entry_paths(entry: dict[str, Any]) -> Iterator[str]:
        """Every source-image path an actor entry can resolve."""

        rotations = entry.get("rotations", {})
        if isinstance(rotations, dict):
            for path in rotations.values():
                if path:
                    yield str(path)
        clips = entry.get("clips", {})
        if not isinstance(clips, dict):
            return
        for clip in clips.values():
            if not isinstance(clip, dict):
                continue
            directions = clip.get("directions", {})
            if not isinstance(directions, dict):
                continue
            for frame_paths in directions.values():
                if not isinstance(frame_paths, (list, tuple)):
                    continue
                for path in frame_paths:
                    if path:
                        yield str(path)

    def prewarm_actor_sources(
        self,
        requests: Iterable[tuple[str, str]],
        progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """Load and decode every source frame for the given (name, kind) actors.

        Floor entry calls this so first-sight and post-eviction source loads
        (disk read + decode + convert) land on the loading transition instead
        of mid-combat frames. Only the source cache is touched: normalized
        per-scale frames still build lazily, which is cheap CPU work per frame
        and keeps the byte-bounded frame LRU from being flooded up front.
        Unknown names resolve to no slug and cost nothing.
        """

        if not self.available:
            return 0
        entries: list[dict[str, Any]] = []
        seen_slugs: set[str] = set()
        for name, kind in requests:
            slug = self._actor_slug(str(name), str(kind or ""))
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            entry = self.manifest["actors"].get(slug)
            if isinstance(entry, dict):
                entries.append(entry)
        warmed = 0
        for index, entry in enumerate(entries):
            for path in self._actor_entry_paths(entry):
                if self._source_surface(path) is not None:
                    warmed += 1
            if progress is not None:
                # Per actor, not per frame: the loading screen repaint is
                # rate-limited anyway, and per-frame callbacks would double
                # the loop's Python overhead for nothing.
                progress(index + 1, len(entries))
        return warmed

    def actor_clip_seconds(
        self, name: str, state: str, *, kind: str = ""
    ) -> float | None:
        """Duration in seconds of an authored actor clip, or None if absent."""

        if not self.available:
            return None
        slug = self._actor_slug(name, kind)
        if slug is None:
            return None
        entry = self.manifest["actors"].get(slug)
        if not isinstance(entry, dict):
            return None
        clip = entry.get("clips", {}).get(state)
        if not isinstance(clip, dict):
            return None
        by_direction = clip.get("directions", {})
        frames = max(
            (len(paths) for paths in by_direction.values() if paths), default=0
        )
        if frames <= 0:
            return None
        fps = max(0.1, float(clip.get("fps", 6.0)))
        return frames / fps

    def resolve_item(
        self, slot: str, *, elapsed: float = 0.0, name: str = ""
    ) -> ResolvedSpriteFrame | None:
        if not self.available:
            return None
        # Named items (uniques, base equipment) carry their own art keyed by
        # the item name as a manifest alias; the slot entry is the fallback.
        # Unidentified gear passes its masked display name, so hidden uniques
        # cannot leak their art before identification.
        key = None
        if name:
            key = self._item_aliases.get(str(name).casefold())
        if key is None:
            key = self._item_aliases.get(str(slot).casefold())
        if key is None:
            return None
        entry = self.manifest["items"].get(key)
        if not isinstance(entry, dict):
            return None
        source_path = str(entry["path"])
        frame_number = 0
        frames = entry.get("frames")
        if isinstance(frames, list) and frames:
            frame_number = self._animation_frame_index(entry, elapsed)
            source_path = str(frames[frame_number % len(frames)])
        return self._normalized_frame(
            source_path, entry, ("item", key, "idle", "none", frame_number)
        )

    def resolve_prop(self, key_or_alias: str) -> ResolvedSpriteFrame | None:
        if not self.available:
            return None
        key = self._prop_aliases.get(str(key_or_alias).casefold())
        if key is None:
            return None
        entry = self.manifest["props"].get(key)
        if not isinstance(entry, dict):
            return None
        return self._normalized_frame(
            str(entry["path"]), entry, ("prop", key, "idle", "none", 0)
        )

    @staticmethod
    def _tinted_surface(
        source: pygame.Surface,
        target: Color,
        strength: float,
        variant: int,
    ) -> pygame.Surface:
        strength = max(0.0, min(1.0, strength))
        result = source.copy()
        multiplier = tuple(
            max(0, min(255, round(255 - (255 - channel) * strength * 0.72)))
            for channel in target
        )
        result.fill((*multiplier, 255), special_flags=pygame.BLEND_RGBA_MULT)
        addition = tuple(round(channel * strength * 0.12) for channel in target)
        result.fill((*addition, 0), special_flags=pygame.BLEND_RGB_ADD)
        delta = (-9, -3, 3, 7)[variant % 4]
        if delta > 0:
            result.fill((delta, delta, delta, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif delta < 0:
            result.fill((-delta, -delta, -delta, 0), special_flags=pygame.BLEND_RGB_SUB)
        return result

    @staticmethod
    def _clip_overlay(overlay: pygame.Surface, base: pygame.Surface) -> pygame.Surface:
        mask = pygame.mask.from_surface(base, 1).to_surface(
            setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)
        )
        overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return overlay

    def _decorate_special_wall(
        self,
        surface: pygame.Surface,
        style: str | None,
        anchor: tuple[int, int],
        accent: Color,
        render_scale_bucket: float = 1.0,
    ) -> None:
        if not style:
            return
        kind, _, side = style.partition(":")
        if side not in ("left", "right"):
            side = style if style in ("left", "right") else "left"
            kind = "quest_room"
        ax, ay = anchor
        sign = -1 if side == "left" else 1
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        # Sub-1.0 buckets (0.8) are valid render scales; only guard against
        # nonpositive values so the decoration tracks its shrunken tile.
        scale = max(0.1, float(render_scale_bucket))
        center = (
            ax + sign * round(62 * scale),
            ay - round(92 * scale),
        )
        width = max(1, round(WORLD_SCALE * scale))
        if kind == "bar":
            wood = (126, 74, 42, 170)
            for offset in (-48, -24, 0, 24, 48):
                offset = round(offset * scale)
                x = center[0] + sign * offset // 3
                pygame.draw.line(
                    overlay,
                    wood,
                    (x - round(38 * scale), center[1] + offset // 2),
                    (
                        x + round(32 * scale),
                        center[1] + offset // 2 + round(18 * scale),
                    ),
                    width * 2,
                )
        elif kind == "garden":
            vine = (72, 148, 78, 205)
            points = [
                (
                    center[0] - sign * round(28 * scale),
                    center[1] + round(56 * scale),
                ),
                (
                    center[0] + sign * round(10 * scale),
                    center[1] + round(24 * scale),
                ),
                (
                    center[0] - sign * round(8 * scale),
                    center[1] - round(8 * scale),
                ),
                (
                    center[0] + sign * round(30 * scale),
                    center[1] - round(42 * scale),
                ),
            ]
            pygame.draw.lines(overlay, vine, False, points, width * 2)
            for point in points[1:]:
                pygame.draw.ellipse(
                    overlay,
                    (96, 178, 92, 190),
                    (
                        point[0] - round(8 * scale),
                        point[1] - round(4 * scale),
                        round(16 * scale),
                        round(9 * scale),
                    ),
                )
        else:
            rune = (*accent, 205)
            radius = round(22 * scale)
            pygame.draw.circle(overlay, rune, center, radius, width * 2)
            pygame.draw.line(
                overlay,
                rune,
                (center[0] - radius, center[1]),
                (center[0] + radius, center[1]),
                width,
            )
            pygame.draw.line(
                overlay,
                rune,
                (center[0], center[1] - radius),
                (center[0], center[1] + radius),
                width,
            )
        surface.blit(self._clip_overlay(overlay, surface), (0, 0))

    def world_animation_frame_count(self, key: str) -> int:
        if not self.available:
            return 1
        entry = self._active_world_manifest().get(key)
        if not isinstance(entry, dict):
            return 1
        return self._world_animation_frame_count(entry)

    def world_animation_frame_index(self, key: str, elapsed: float) -> int:
        if not self.available:
            return 0
        entry = self._active_world_manifest().get(key)
        if not isinstance(entry, dict):
            return 0
        return self._animation_frame_index(entry, elapsed)

    def _active_world_manifest(self) -> dict[str, Any]:
        """Return the selected authored-world map.

        Older/custom asset roots may not ship the optional Modern companion
        manifest. In that case the primary map remains a per-resource fallback
        instead of disabling authored graphics altogether.
        """

        return self._world_manifests.get(
            self.world_graphics_tier,
            self.manifest.get("world", {}),
        )

    def set_world_graphics_tier(self, graphics_tier: str) -> None:
        selected = normalize_graphics_tier(
            graphics_tier,
            default=GRAPHICS_TIER_HD,
        )
        if selected != GRAPHICS_TIER_MODERN:
            selected = GRAPHICS_TIER_HD
        if selected == self.world_graphics_tier:
            return
        self.world_graphics_tier = selected
        self._world_cache.clear()

    @staticmethod
    def _world_animation_frame_count(entry: dict[str, Any]) -> int:
        overlay_frames = entry.get("overlay_frames")
        if isinstance(overlay_frames, list) and overlay_frames:
            # Overlay animations have an implicit frame zero: the selected
            # base variant with no overlay. Frames 1..N add overlays 0..N-1.
            return len(overlay_frames) + 1
        frames = entry.get("frames")
        return len(frames) if isinstance(frames, list) and frames else 1

    @staticmethod
    def _animation_frame_index(entry: dict[str, Any], elapsed: float) -> int:
        frame_count = AssetSpriteLibrary._world_animation_frame_count(entry)
        if frame_count <= 1:
            return 0
        fps = max(0.01, float(entry.get("fps", 6.0)))
        step = int(max(0.0, elapsed) * fps)
        if bool(entry.get("ping_pong", False)):
            sequence_length = frame_count * 2 - 2
            step %= sequence_length
            if step >= frame_count:
                step = sequence_length - step
            return step
        return step % frame_count

    def resolve_world(
        self,
        key: str,
        *,
        target_canvas: tuple[int, int],
        target_anchor: tuple[int, int],
        tint: Color,
        accent: Color,
        variant: int,
        mirror: bool = False,
        wall_face_style: str | None = None,
        animation_frame: int = 0,
        render_scale_bucket: float = 1.0,
    ) -> tuple[pygame.Surface, int, int] | None:
        if not self.available:
            return None
        entry = self._active_world_manifest().get(key)
        if not isinstance(entry, dict):
            return None
        requested_scale = float(render_scale_bucket)
        render_scale_bucket = 1.6
        for candidate in (0.8, 1.0, 1.2, 1.4, 1.6):
            if candidate + 1e-9 >= requested_scale:
                render_scale_bucket = candidate
                break
        source_path = str(entry["path"])
        variants = entry.get("variants")
        authored_variant_index: int | None = None
        if isinstance(variants, list) and variants:
            authored_variant_index = variant % len(variants)
            source_path = str(variants[authored_variant_index])
        frames = entry.get("frames")
        if isinstance(frames, list) and frames:
            source_path = str(frames[animation_frame % len(frames)])
        overlay_path: str | None = None
        overlay_frames = entry.get("overlay_frames")
        if (
            isinstance(overlay_frames, list)
            and overlay_frames
            and animation_frame > 0
        ):
            overlay_path = str(
                overlay_frames[(animation_frame - 1) % len(overlay_frames)]
            )
        cache_key = (
            self.world_graphics_tier,
            key,
            source_path,
            overlay_path,
            target_canvas,
            target_anchor,
            tuple(tint),
            tuple(accent),
            authored_variant_index,
            variant % 4,
            mirror,
            wall_face_style,
            render_scale_bucket,
        )
        cached = self._world_cache.get(cache_key)
        if cached is not None:
            return cached
        source = self._source_surface(source_path)
        if source is None:
            return None
        if overlay_path is not None:
            overlay = self._source_surface(overlay_path)
            if overlay is None:
                return None
            if overlay.get_size() != source.get_size():
                LOGGER.warning(
                    "World overlay %s size %s does not match base %s size %s",
                    overlay_path,
                    overlay.get_size(),
                    source_path,
                    source.get_size(),
                )
                return None
            source = source.copy()
            base_alpha = source.copy()
            base_alpha.fill(
                (0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT
            )
            # Guidance is a material overlay, not a second tile silhouette.
            # Clip it to the selected base before compositing so transparent
            # margins and the canonical floor alpha remain unchanged. Restore
            # the exact base alpha after source-over blending as this manifest
            # field also supports partially transparent third-party masters.
            source.blit(self._clip_overlay(overlay.copy(), source), (0, 0))
            source.fill(
                (255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MULT
            )
            source.blit(base_alpha, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        should_flip = mirror
        if key in (
            "floor",
            "guiding_floor",
            "garden_floor",
            "bar_floor",
            "quest_floor",
            "shop_floor",
        ) and authored_variant_index is None:
            should_flip = should_flip ^ bool(variant % 2)
        if should_flip:
            source = pygame.transform.flip(source, True, False)
        bounds = source.get_bounding_rect(min_alpha=1)
        if bounds.width <= 0 or bounds.height <= 0:
            return None
        padding = 2
        available_width = max(1, target_canvas[0] - padding * 2)
        available_height = max(1, target_canvas[1] - padding * 2)
        reference_width = float(entry.get("reference_width", source.get_width()))
        desired_scale = (
            TILE_W * render_scale_bucket / max(1.0, reference_width)
        )
        scale = min(
            desired_scale,
            available_width / bounds.width,
            available_height / bounds.height,
        )
        original_size = source.get_size()
        output_size = (
            max(1, round(original_size[0] * scale)),
            max(1, round(original_size[1] * scale)),
        )
        if output_size != original_size:
            source = pygame.transform.scale(source, output_size)
        # The tint operations are pointwise and alpha-preserving, so they
        # commute exactly with nearest-neighbor scaling. Tint the smaller
        # resolved surface instead of every pixel in a high-resolution master.
        source = self._tinted_surface(
            source, tint, float(entry.get("tint_strength", 0.5)), variant
        )
        scale_x = output_size[0] / original_size[0]
        scale_y = output_size[1] / original_size[1]
        canvas = pygame.Surface(target_canvas, pygame.SRCALPHA)
        source_anchor = entry.get(
            "source_anchor", (original_size[0] / 2, original_size[1] / 2)
        )
        scaled_anchor = (
            round(float(source_anchor[0]) * scale_x),
            round(float(source_anchor[1]) * scale_y),
        )
        scaled_bounds = source.get_bounding_rect(min_alpha=1)
        destination_x = target_anchor[0] - scaled_anchor[0]
        destination_y = target_anchor[1] - scaled_anchor[1]
        destination_x = max(
            padding - scaled_bounds.left,
            min(
                destination_x,
                target_canvas[0] - padding - scaled_bounds.right,
            ),
        )
        destination_y = max(
            padding - scaled_bounds.top,
            min(
                destination_y,
                target_canvas[1] - padding - scaled_bounds.bottom,
            ),
        )
        canvas.blit(source, (destination_x, destination_y))
        self._decorate_special_wall(
            canvas,
            wall_face_style,
            target_anchor,
            accent,
            render_scale_bucket,
        )
        try:
            canvas = canvas.convert_alpha()
        except pygame.error:
            pass
        canvas = optimize_immutable_alpha_surface(canvas)
        result = (canvas, target_anchor[0], target_anchor[1])
        return self._world_cache.put(cache_key, result)

    def clear_derived_caches(self) -> None:
        self._frame_cache.clear()
        self._world_cache.clear()
        self._resolved_actor_cache.clear()

    def cache_stats(self) -> dict[str, int]:
        return {
            "decoded_sources": len(self._source_cache),
            "resolved_frames": len(self._frame_cache),
            "actor_resolution_keys": len(self._resolved_actor_cache),
            "world_surfaces": len(self._world_cache),
            "world_surface_bytes": self._world_cache.weight,
            "missing_resources": len(self._missing_resources),
            "source_loads": self.source_load_count,
            "frame_builds": self.frame_build_count,
        }


@lru_cache(maxsize=1)
def _shared_procedural_atlas() -> PixelSpriteAtlas:
    """Build the immutable procedural fallback surfaces once per process."""
    return PixelSpriteAtlas()


class SpriteAtlas:
    """Asset-first sprite facade with the procedural atlas as a safe fallback."""

    def __init__(
        self,
        *,
        legacy_graphics: bool = False,
        graphics_tier: str | None = None,
        authored_graphics_tier: str | None = None,
        asset_root: Path | Traversable | None = None,
        cache_profile: str = "desktop",
    ) -> None:
        # PixelSpriteAtlas eagerly builds static surfaces and never mutates them
        # after construction. Share that expensive fallback while keeping the
        # asset library and every derived facade cache instance-local.
        self.legacy = _shared_procedural_atlas()
        if graphics_tier is None:
            graphics_tier = (
                GRAPHICS_TIER_LEGACY
                if legacy_graphics
                else GRAPHICS_TIER_DEFAULT
            )
        self.graphics_tier = normalize_graphics_tier(graphics_tier)
        self.legacy_graphics = self.graphics_tier == GRAPHICS_TIER_LEGACY
        if self.legacy_graphics:
            remembered_tier = normalize_graphics_tier(
                authored_graphics_tier,
                default=GRAPHICS_TIER_DEFAULT,
            )
            if remembered_tier == GRAPHICS_TIER_LEGACY:
                remembered_tier = GRAPHICS_TIER_DEFAULT
            self._authored_graphics_tier = remembered_tier
        else:
            self._authored_graphics_tier = self.graphics_tier
        self.assets = AssetSpriteLibrary(
            asset_root,
            world_graphics_tier=self._authored_graphics_tier,
            cache_profile=cache_profile,
        )
        self._prop_variant_cache: dict[tuple[object, ...], ResolvedSpriteFrame] = {}
        self._preview_cache: dict[tuple[object, ...], pygame.Surface] = {}
        self._normal_map_cache: _LruCache[
            int, tuple[pygame.Surface, pygame.Surface]
        ] = _LruCache(320)
        self._refresh_public_surfaces()

    def __getattr__(self, name: str):
        return getattr(self.legacy, name)

    @property
    def authored_graphics_active(self) -> bool:
        return not self.legacy_graphics and self.assets.available

    @property
    def modern_graphics_active(self) -> bool:
        """Compatibility alias for any authored-asset mode.

        This name predates the Modern/HD split and is intentionally not
        narrowed: existing actor, prop, menu, and HUD call sites use it to
        distinguish authored assets from procedural Legacy graphics.
        """

        return self.authored_graphics_active

    @property
    def modern_world_active(self) -> bool:
        return (
            self.graphics_tier == GRAPHICS_TIER_MODERN
            and self.assets.available
            and self.assets.modern_world_available
        )

    @property
    def authored_graphics_tier(self) -> str:
        return self._authored_graphics_tier

    @property
    def hd_graphics_active(self) -> bool:
        return (
            self.graphics_tier == GRAPHICS_TIER_HD
            and self.assets.available
        )

    def _fallback_frame(
        self, surface: pygame.Surface, *key: object
    ) -> ResolvedSpriteFrame:
        return ResolvedSpriteFrame(
            surface,
            (surface.get_width() // 2, surface.get_height()),
            "legacy",
            tuple(key),
        )

    def set_legacy_graphics(self, enabled: bool) -> None:
        self.set_graphics_tier(
            GRAPHICS_TIER_LEGACY
            if enabled
            else self._authored_graphics_tier
        )

    def set_authored_graphics_tier(self, graphics_tier: str) -> None:
        """Remember which authored tier Legacy should return to."""

        selected = normalize_graphics_tier(graphics_tier)
        if selected == GRAPHICS_TIER_LEGACY:
            selected = GRAPHICS_TIER_DEFAULT
        if not self.legacy_graphics:
            selected = self.graphics_tier
        if selected == self._authored_graphics_tier:
            return
        self._authored_graphics_tier = selected
        if self.legacy_graphics:
            self.assets.set_world_graphics_tier(selected)

    def set_graphics_tier(self, graphics_tier: str) -> None:
        selected = normalize_graphics_tier(graphics_tier)
        if selected == self.graphics_tier:
            return
        if selected != GRAPHICS_TIER_LEGACY:
            self._authored_graphics_tier = selected
        self.graphics_tier = selected
        self.legacy_graphics = selected == GRAPHICS_TIER_LEGACY
        self.assets.set_world_graphics_tier(self._authored_graphics_tier)
        self.assets.clear_derived_caches()
        self._prop_variant_cache.clear()
        self._preview_cache.clear()
        self._normal_map_cache.clear()
        self._refresh_public_surfaces()

    def clear_derived_caches(self) -> None:
        self.assets.clear_derived_caches()
        self._prop_variant_cache.clear()
        self._preview_cache.clear()
        self._normal_map_cache.clear()

    def clear_normal_map_cache(self) -> None:
        self._normal_map_cache.clear()

    def _asset_actor(
        self,
        name: str,
        state: str,
        direction: str,
        clip_time: float,
        *,
        kind: str = "",
        clip_progress: float | None = None,
        loop_progress: float | None = None,
        native: bool = False,
    ) -> ResolvedSpriteFrame | None:
        if not self.modern_graphics_active:
            return None
        return self.assets.resolve_actor(
            name,
            state,
            direction,
            clip_time,
            kind=kind,
            clip_progress=clip_progress,
            loop_progress=loop_progress,
            native=native,
        )

    def actor_clip_seconds(
        self, name: str, state: str, *, kind: str = ""
    ) -> float | None:
        if not self.modern_graphics_active:
            return None
        return self.assets.actor_clip_seconds(name, state, kind=kind)

    def prewarm_actor_sources(
        self,
        requests: Iterable[tuple[str, str]],
        progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """Front-load actor source frames; a no-op on procedural Legacy."""

        if not self.modern_graphics_active:
            return 0
        return self.assets.prewarm_actor_sources(requests, progress=progress)

    def player_visual(
        self,
        class_name: str,
        state: str,
        anim_time: float,
        elapsed: float,
        *,
        direction: str = "south",
        action_time: float | None = None,
        action_progress: float | None = None,
        native: bool = False,
    ) -> ResolvedSpriteFrame:
        clip_time = (
            action_time
            if state in _ACTION_STATES and action_time is not None
            else anim_time
            if state == "walk"
            else elapsed
        )
        asset = self._asset_actor(
            class_name,
            state,
            direction,
            clip_time,
            clip_progress=action_progress,
            native=native,
        )
        if asset is not None:
            return asset
        surface = self.legacy.player_frame(
            class_name,
            state,
            anim_time,
            elapsed,
            action_time=action_time,
            action_progress=action_progress,
        )
        return self._fallback_frame(surface, "player", class_name, state)

    def legacy_player_base(self, class_name: str) -> pygame.Surface:
        return self.legacy.player_sprites.get(class_name, self.legacy.player)

    def player_frame(
        self,
        class_name: str,
        state: str,
        anim_time: float,
        elapsed: float,
        direction: str = "south",
        *,
        action_time: float | None = None,
        action_progress: float | None = None,
    ) -> pygame.Surface:
        return self.player_visual(
            class_name,
            state,
            anim_time,
            elapsed,
            direction=direction,
            action_time=action_time,
            action_progress=action_progress,
        ).surface

    def enemy_visual(
        self,
        name: str,
        kind: str,
        state: str,
        anim_time: float,
        elapsed: float,
        *,
        direction: str = "south",
        action_time: float | None = None,
        action_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        clip_time = (
            action_time
            if state in _ACTION_STATES and action_time is not None
            else anim_time
            if state == "walk"
            else elapsed
        )
        asset = self._asset_actor(
            name,
            state,
            direction,
            clip_time,
            kind=kind,
            clip_progress=action_progress,
        )
        if asset is not None:
            return asset
        surface = self.legacy.enemy_frame(
            name,
            kind,
            state,
            anim_time,
            elapsed,
            action_time=action_time,
            action_progress=action_progress,
        )
        return self._fallback_frame(surface, "enemy", name, state)

    def enemy_frame(
        self,
        name: str,
        kind: str,
        state: str,
        anim_time: float,
        elapsed: float,
        direction: str = "south",
        *,
        action_time: float | None = None,
        action_progress: float | None = None,
    ) -> pygame.Surface:
        return self.enemy_visual(
            name,
            kind,
            state,
            anim_time,
            elapsed,
            direction=direction,
            action_time=action_time,
            action_progress=action_progress,
        ).surface

    def legacy_enemy_base(self, name: str, kind: str) -> pygame.Surface:
        key = self.legacy.enemy_key(name, kind)
        return self.legacy.enemies.get(key, self.legacy.enemies["Ghoul"])

    def boss_frame(
        self,
        state: str,
        anim_time: float,
        elapsed: float,
        direction: str = "south",
        *,
        action_time: float | None = None,
        action_progress: float | None = None,
    ) -> pygame.Surface:
        clip_time = (
            action_time
            if state in _ACTION_STATES and action_time is not None
            else anim_time
            if state == "walk"
            else elapsed
        )
        asset = self._asset_actor(
            "Gate Tyrant",
            state,
            direction,
            clip_time,
            kind="boss",
            clip_progress=action_progress,
        )
        if asset is not None:
            return asset.surface
        return self.legacy.boss_frame(
            state,
            anim_time,
            elapsed,
            action_time=action_time,
            action_progress=action_progress,
        )

    def item_visual(
        self, slot: str, elapsed: float, rarity: str = "Common", name: str = ""
    ) -> ResolvedSpriteFrame:
        if self.modern_graphics_active:
            asset = self.assets.resolve_item(slot, elapsed=elapsed, name=name)
            if asset is not None:
                return asset
        surface = self.legacy.item_frame(slot, elapsed, rarity)
        return self._fallback_frame(surface, "item", slot, rarity)

    def item_frame(
        self, slot: str, elapsed: float, rarity: str = "Common", name: str = ""
    ) -> pygame.Surface:
        return self.item_visual(slot, elapsed, rarity, name).surface

    def item_preview(self, slot: str, size: int, name: str = "") -> pygame.Surface:
        size = max(1, int(size))
        cache_key = ("item-preview", self.graphics_tier, slot, name, size)
        cached = self._preview_cache.get(cache_key)
        if cached is not None:
            return cached
        source = self.item_visual(slot, 0.0, name=name).surface
        scale = min(size / source.get_width(), size / source.get_height())
        preview = pygame.transform.scale(
            source,
            (
                max(1, round(source.get_width() * scale)),
                max(1, round(source.get_height() * scale)),
            ),
        )
        self._preview_cache[cache_key] = preview
        return preview

    def shopkeeper_visual(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        state = "walk" if moving else "dance" if dancing else "idle"
        asset = self._asset_actor(
            "shopkeeper",
            state,
            direction,
            elapsed,
            loop_progress=clip_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.shopkeeper_frame(
                elapsed, moving=moving, clip_progress=clip_progress
            ),
            "npc",
            "shopkeeper",
            state,
        )

    def shopkeeper_frame(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> pygame.Surface:
        return self.shopkeeper_visual(
            elapsed,
            direction=direction,
            moving=moving,
            dancing=dancing,
            clip_progress=clip_progress,
        ).surface

    def story_guest_visual(
        self,
        elapsed: float,
        resolved: bool = False,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        state = "walk" if moving else "dance" if dancing else "idle"
        asset = self._asset_actor(
            "story_guest",
            state,
            direction,
            elapsed,
            loop_progress=clip_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.story_guest_frame(
                elapsed,
                resolved,
                moving=moving,
                clip_progress=clip_progress,
            ),
            "npc",
            "story_guest",
            state,
        )

    def story_guest_frame(
        self,
        elapsed: float,
        resolved: bool = False,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> pygame.Surface:
        return self.story_guest_visual(
            elapsed,
            resolved,
            direction=direction,
            moving=moving,
            dancing=dancing,
            clip_progress=clip_progress,
        ).surface

    def bar_dancer_visual(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        state = "walk" if moving else "dance" if dancing else "idle"
        asset = self._asset_actor(
            "Bar Dancer",
            state,
            direction,
            elapsed,
            loop_progress=clip_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.bar_dancer_frame(
                elapsed,
                moving=moving,
                dancing=dancing,
                clip_progress=clip_progress,
            ),
            "npc",
            "bar_dancer",
            state,
        )

    def bar_dancer_frame(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> pygame.Surface:
        return self.bar_dancer_visual(
            elapsed,
            direction=direction,
            moving=moving,
            dancing=dancing,
            clip_progress=clip_progress,
        ).surface

    def lossless_soul_visual(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        state = "walk" if moving else "dance" if dancing else "idle"
        asset = self._asset_actor(
            "Lossless Soul",
            state,
            direction,
            elapsed,
            loop_progress=clip_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.lossless_soul_frame(
                elapsed,
                moving=moving,
                dancing=dancing,
                clip_progress=clip_progress,
            ),
            "npc",
            "lossless_soul",
            state,
        )

    def lossless_soul_frame(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> pygame.Surface:
        return self.lossless_soul_visual(
            elapsed,
            direction=direction,
            moving=moving,
            dancing=dancing,
            clip_progress=clip_progress,
        ).surface

    def lossless_soul_prop_visual(self, anchor_key: str) -> ResolvedSpriteFrame | None:
        """Authored furnishing sprite for a soul-hall anchor, if available."""
        asset_key = LOSSLESS_SOUL_PROP_ASSET_KEYS.get(anchor_key)
        if asset_key is None:
            return None
        return self._asset_prop(asset_key)

    def bar_prop_visual(self, anchor_key: str) -> ResolvedSpriteFrame | None:
        """Authored furnishing sprite for a bar anchor (barrel / table)."""
        if anchor_key.startswith("bar_barrel_"):
            return self._asset_prop("bar_barrel")
        if anchor_key.startswith("bar_table_"):
            return self._asset_prop("bar_table")
        return None

    def garden_frog_visual(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        state = "walk" if moving else "dance" if dancing else "idle"
        asset = self._asset_actor(
            "Garden Frog",
            state,
            direction,
            elapsed,
            loop_progress=clip_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.garden_frog_frame(
                elapsed, moving=moving, clip_progress=clip_progress
            ),
            "npc",
            "garden_frog",
            state,
        )

    def garden_frog_frame(
        self,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        dancing: bool = False,
        clip_progress: float | None = None,
    ) -> pygame.Surface:
        return self.garden_frog_visual(
            elapsed,
            direction=direction,
            moving=moving,
            dancing=dancing,
            clip_progress=clip_progress,
        ).surface

    def familiar_visual(
        self,
        variant: int,
        elapsed: float,
        *,
        direction: str = "south",
        moving: bool = False,
        kind: str = "spirit",
        petting: bool = False,
        pet_progress: float | None = None,
        attacking: bool = False,
        attack_progress: float | None = None,
    ) -> ResolvedSpriteFrame:
        if kind == "bar_dancer":
            # The immortal Bar Dancer companion reuses her bar-NPC actor art
            # wholesale: she dances in place while idle and walks when
            # following; her dance doubles as the attack flourish.
            return self.bar_dancer_visual(
                elapsed,
                direction=direction,
                moving=moving,
                dancing=not moving,
            )
        if kind == "spirit_beast":
            key = "spirit_beast"
            state = (
                "pet"
                if petting
                else "attack"
                if attacking
                else "walk"
                if moving
                else "idle"
            )
            fallback_variant = 2
        else:
            key = "familiar_crow" if variant else "familiar_wisp"
            state = "walk" if moving else "idle"
            fallback_variant = variant
        action_progress = (
            pet_progress if petting else attack_progress if attacking else None
        )
        asset = self._asset_actor(
            key,
            state,
            direction,
            elapsed,
            clip_progress=action_progress,
        )
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.familiar_frame(
                fallback_variant,
                elapsed,
                state=state,
                action_progress=action_progress,
            ),
            "familiar",
            kind,
            fallback_variant,
            state,
        )

    def familiar_frame(self, variant: int, elapsed: float) -> pygame.Surface:
        return self.familiar_visual(variant, elapsed).surface

    def _asset_prop(self, key: str) -> ResolvedSpriteFrame | None:
        if not self.modern_graphics_active:
            return None
        return self.assets.resolve_prop(key)

    def _prop_variant(
        self,
        frame: ResolvedSpriteFrame,
        key: str,
        *,
        scale: float = 1.0,
        multiplier: tuple[int, int, int] = (255, 255, 255),
    ) -> ResolvedSpriteFrame:
        cache_key = (key, round(scale, 3), multiplier)
        cached = self._prop_variant_cache.get(cache_key)
        if cached is not None:
            return cached
        surface = frame.surface
        anchor = frame.anchor
        if multiplier != (255, 255, 255):
            color_key = surface.get_colorkey()
            if color_key is not None:
                # Android converts immutable alpha sprites to magenta-colorkey
                # RLE surfaces. Multiplying that background changes the key
                # pixels and exposes a solid box (most visibly after a shrine
                # becomes the dimmed "used" variant), so restore real alpha
                # before applying any color transform.
                alpha_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
                alpha_surface.blit(surface, (0, 0))
                surface = alpha_surface
            else:
                surface = surface.copy()
            surface.fill((*multiplier, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if abs(scale - 1.0) > 0.001:
            surface = pygame.transform.scale(
                surface,
                (
                    max(1, round(surface.get_width() * scale)),
                    max(1, round(surface.get_height() * scale)),
                ),
            )
            anchor = (round(anchor[0] * scale), round(anchor[1] * scale))
        surface = optimize_immutable_alpha_surface(surface)
        variant = ResolvedSpriteFrame(
            surface, anchor, "asset", ("prop-variant", *cache_key)
        )
        self._prop_variant_cache[cache_key] = variant
        return variant

    def trap_visual(self, kind: str, elapsed: float) -> ResolvedSpriteFrame:
        key = {
            "Spike Trap": "trap_spike",
            "Rune Trap": "trap_rune",
            "Poison Needle": "trap_poison",
        }.get(kind, "trap_spike")
        asset = self._asset_prop(key)
        if asset is not None:
            return asset
        return self._fallback_frame(
            self.legacy.trap_frame(kind, elapsed), "trap", kind
        )

    def trap_frame(self, kind: str, elapsed: float) -> pygame.Surface:
        return self.trap_visual(kind, elapsed).surface

    def shrine_visual(
        self, kind: str, elapsed: float, used: bool = False
    ) -> ResolvedSpriteFrame:
        asset = self._asset_prop("shrine")
        if asset is not None:
            return (
                self._prop_variant(asset, "shrine-used", multiplier=(105, 105, 115))
                if used
                else asset
            )
        return self._fallback_frame(
            self.legacy.shrine_frame(kind, elapsed, used), "shrine", used
        )

    def shrine_frame(
        self, kind: str, elapsed: float, used: bool = False
    ) -> pygame.Surface:
        return self.shrine_visual(kind, elapsed, used).surface

    def secret_visual(self, elapsed: float) -> ResolvedSpriteFrame:
        asset = self._asset_prop("secret_cache")
        if asset is not None:
            return asset
        return self._fallback_frame(self.legacy.secret_frame(elapsed), "secret")

    def secret_frame(self, elapsed: float) -> pygame.Surface:
        return self.secret_visual(elapsed).surface

    def shop_sign_visual(self) -> ResolvedSpriteFrame:
        asset = self._asset_prop("shop_sign")
        if asset is not None:
            return asset
        return self._fallback_frame(self.legacy.shop_sign_sprite, "shop-sign")

    def gold_stack_visual(
        self, size: int, variant: int = 0
    ) -> ResolvedSpriteFrame:
        size = max(1, min(3, int(size)))
        variant = int(variant) % len(GOLD_STACK_ASSET_KEYS)
        asset_key = GOLD_STACK_ASSET_KEYS[variant]
        asset = self._asset_prop(asset_key)
        if asset is None and asset_key != "gold_stack":
            asset = self._asset_prop("gold_stack")
        if asset is not None:
            scale = {1: 0.72, 2: 0.92, 3: 1.14}[size]
            return self._prop_variant(
                asset,
                f"gold-stack-{variant}-{size}",
                scale=scale,
            )
        return self._fallback_frame(
            self.legacy.gold_stack_sprite(size), "gold-stack", size
        )

    def gold_stack_sprite(self, size: int, variant: int = 0) -> pygame.Surface:
        return self.gold_stack_visual(size, variant).surface

    def ambush_bell_visual(self) -> ResolvedSpriteFrame | None:
        return self._asset_prop("ambush_bell")

    def stage_prop_visual(
        self, kind: str, scale: float = 1.0
    ) -> ResolvedSpriteFrame | None:
        """4.2.x theater redesign: authored sprite for a cutscene stage prop.

        Returns ``None`` for unknown kinds, in legacy graphics mode, or when
        the asset is missing so the stage renderer can fall back to its
        procedural prop painters. Scaled variants (anchor included) are cached
        through the shared prop-variant cache, so per-frame stage draws blit
        prebuilt surfaces.
        """
        key = STAGE_PROP_ASSET_KEYS.get(kind)
        if key is None:
            return None
        asset = self._asset_prop(key)
        if asset is None:
            return None
        if abs(scale - 1.0) <= 0.001:
            return asset
        return self._prop_variant(asset, f"stage-{kind}", scale=scale)

    def bar_wall_sconce_visual(
        self, side: str
    ) -> ResolvedSpriteFrame | None:
        direction = BAR_WALL_SCONCE_DIRECTION_BY_FACE.get(side)
        if direction is None:
            return None
        return self._asset_prop(
            f"bar_wall_sconce_{direction.replace('-', '_')}"
        )

    def world_tile_animation_frame_count(self, key: str) -> int:
        if not self.modern_graphics_active:
            return 1
        return self.assets.world_animation_frame_count(key)

    def world_tile_animation_frame(self, key: str, elapsed: float) -> int:
        if not self.modern_graphics_active:
            return 0
        return self.assets.world_animation_frame_index(key, elapsed)

    def world_tile_surface(
        self,
        key: str,
        *,
        target_canvas: tuple[int, int],
        target_anchor: tuple[int, int],
        tint: Color,
        accent: Color,
        variant: int,
        mirror: bool = False,
        wall_face_style: str | None = None,
        animation_frame: int = 0,
        render_scale_bucket: float = 1.0,
    ) -> tuple[pygame.Surface, int, int] | None:
        if not self.modern_graphics_active:
            return None
        return self.assets.resolve_world(
            key,
            target_canvas=target_canvas,
            target_anchor=target_anchor,
            tint=tint,
            accent=accent,
            variant=variant,
            mirror=mirror,
            wall_face_style=wall_face_style,
            animation_frame=animation_frame,
            render_scale_bucket=render_scale_bucket,
        )

    def _refresh_public_surfaces(self) -> None:
        self.player_sprites = dict(self.legacy.player_sprites)
        self.enemies = dict(self.legacy.enemies)
        self.items = dict(self.legacy.items)
        self.story_guest_sprites = dict(self.legacy.story_guest_sprites)
        self.familiar_sprites = dict(self.legacy.familiar_sprites)
        self.trap_sprites = dict(self.legacy.trap_sprites)
        self.shrine_sprites = dict(self.legacy.shrine_sprites)
        self.secret_sprites = dict(self.legacy.secret_sprites)
        self.gold_stack_sprites = dict(self.legacy.gold_stack_sprites)
        self.shopkeeper_sprite = self.legacy.shopkeeper_sprite
        self.shop_sign_sprite = self.legacy.shop_sign_sprite
        if self.modern_graphics_active:
            for class_name in tuple(self.player_sprites):
                frame = self.assets.resolve_actor(
                    class_name, "idle", "south", 0.0
                )
                if frame is not None:
                    self.player_sprites[class_name] = frame.surface
            for enemy_name in tuple(self.enemies):
                frame = self.assets.resolve_actor(
                    enemy_name, "idle", "south", 0.0, kind="melee"
                )
                if frame is not None:
                    self.enemies[enemy_name] = frame.surface
            for slot in tuple(self.items):
                frame = self.assets.resolve_item(slot)
                if frame is not None:
                    self.items[slot] = frame.surface
            guest = self.assets.resolve_actor("story_guest", "idle", "south", 0.0)
            if guest is not None:
                self.story_guest_sprites = {
                    "active": guest.surface,
                    "resolved": guest.surface,
                }
            shopkeeper = self.assets.resolve_actor(
                "shopkeeper", "idle", "south", 0.0
            )
            if shopkeeper is not None:
                self.shopkeeper_sprite = shopkeeper.surface
            for variant, key in ((0, "familiar_wisp"), (1, "familiar_crow")):
                familiar = self.assets.resolve_actor(key, "idle", "south", 0.0)
                if familiar is not None:
                    self.familiar_sprites[variant] = familiar.surface
            for kind, key in (
                ("Spike Trap", "trap_spike"),
                ("Rune Trap", "trap_rune"),
                ("Poison Needle", "trap_poison"),
            ):
                prop = self.assets.resolve_prop(key)
                if prop is not None:
                    self.trap_sprites[kind] = prop.surface
            shrine = self.assets.resolve_prop("shrine")
            if shrine is not None:
                self.shrine_sprites["active"] = shrine.surface
            cache = self.assets.resolve_prop("secret_cache")
            if cache is not None:
                self.secret_sprites["cache"] = cache.surface
            sign = self.assets.resolve_prop("shop_sign")
            if sign is not None:
                self.shop_sign_sprite = sign.surface
            gold = self.assets.resolve_prop("gold_stack")
            if gold is not None:
                for size in (1, 2, 3):
                    self.gold_stack_sprites[size] = self.gold_stack_visual(size).surface
        self.player = self.player_sprites.get("Warden", self.legacy.player)

    def normal_map_for(self, surface: pygame.Surface) -> pygame.Surface | None:
        if not getattr(self.legacy, "_normal_maps_enabled", True):
            return None
        key = id(surface)
        cached = self._normal_map_cache.get(key)
        if cached is not None and cached[0] is surface:
            return cached[1]
        try:
            width, height = surface.get_size()
            long_side = max(width, height)
            source = surface
            if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
                factor = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
                source = pygame.transform.scale(
                    surface,
                    (
                        max(1, int(width * factor)),
                        max(1, int(height * factor)),
                    ),
                )
            # Lazy import avoids a module-load cycle between the
            # ``sprites`` package and the ``rendering`` package.
            from arch_rogue.rendering.lighting import bake_normal_map

            normal = bake_normal_map(source)
        except (MemoryError, pygame.error):
            return None
        self._normal_map_cache.put(key, (surface, normal))
        return normal

    def cache_stats(self) -> dict[str, int]:
        stats = self.assets.cache_stats()
        stats["normal_maps"] = len(self._normal_map_cache)
        return stats
