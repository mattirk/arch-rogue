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
from collections import OrderedDict
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import Any

import pygame

from .mobile import optimize_immutable_alpha_surface


class UiAssetLibrary:
    """Validated, lazy loader and renderer for optional UI sprite assets.

    A missing or malformed manifest disables this library without affecting the
    rest of the game's asset pipeline. Individual image failures are contained
    and negatively cached so callers can safely fall back to procedural UI.
    Cached surfaces are shared and should be treated as read-only by callers.
    """

    MANIFEST_NAME = "ui_manifest.json"
    SOURCE_CACHE_LIMIT = 16
    RENDER_CACHE_LIMIT = 256
    RENDER_MODES = frozenset(("cover", "scale", "nine_slice"))

    def __init__(self, root: Path | Traversable | None = None) -> None:
        self.manifest: dict[str, Any] = {}
        self.available = False
        self.load_error = ""
        self.source_decode_count = 0
        self.render_build_count = 0
        self._source_cache: OrderedDict[str, pygame.Surface | None] = OrderedDict()
        self._render_cache: OrderedDict[
            tuple[
                str,
                str,
                str,
                tuple[int, int, int, int] | None,
                bool,
                int,
                int,
            ],
            pygame.Surface,
        ] = OrderedDict()

        try:
            self.root: Path | Traversable = (
                root
                if root is not None
                else resources.files("arch_rogue.assets").joinpath("sprites")
            )
        except (AttributeError, ModuleNotFoundError, OSError, RuntimeError) as exc:
            self.load_error = self._error_text("UI asset root is unavailable", exc)
            return
        self._load_manifest()

    @staticmethod
    def _error_text(prefix: str, error: BaseException) -> str:
        detail = str(error).strip()
        if detail:
            return f"{prefix}: {detail}"
        return f"{prefix}: {type(error).__name__}"

    def _load_manifest(self) -> None:
        try:
            raw = self.root.joinpath(self.MANIFEST_NAME).read_text(encoding="utf-8")
            data = json.loads(raw)
            self._validate_manifest(data)
        except (
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            self.load_error = self._error_text("UI asset manifest could not be loaded", exc)
            return

        self.manifest = data
        self.available = True
        self.load_error = ""

    def _validate_manifest(self, data: object) -> None:
        if not isinstance(data, dict):
            raise ValueError("UI asset manifest root must be an object")
        format_version = data.get("format_version")
        if type(format_version) is not int or format_version != 1:
            raise ValueError("unsupported UI asset manifest format_version")
        assets = data.get("assets")
        if not isinstance(assets, dict):
            raise ValueError("UI asset manifest has no assets map")

        for key, entry in assets.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("UI asset keys must be non-empty strings")
            if not isinstance(entry, dict):
                raise ValueError(f"UI asset {key!r} must be an object")

            path_value = entry.get("path")
            self._validated_path(path_value, key)

            render_mode = entry.get("render")
            if not isinstance(render_mode, str) or render_mode not in self.RENDER_MODES:
                raise ValueError(f"UI asset {key!r} has an invalid render mode")

            if render_mode == "nine_slice" and "insets" not in entry:
                raise ValueError(f"nine-slice UI asset {key!r} has no insets")
            if "insets" in entry:
                self._validated_insets(entry["insets"], key)
            if "content_insets" in entry:
                self._validated_insets(entry["content_insets"], key)
            scale_insets = entry.get("scale_insets_with_height", False)
            if type(scale_insets) is not bool:
                raise ValueError(
                    f"UI asset {key!r} has an invalid scale-insets flag"
                )
            if scale_insets and render_mode != "nine_slice":
                raise ValueError(
                    f"UI asset {key!r} can scale insets only in nine-slice mode"
                )

    @staticmethod
    def _validated_path(value: object, key: str = "") -> PurePosixPath:
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise ValueError(f"UI asset {key!r} has an invalid PNG path")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix.casefold() != ".png":
            raise ValueError(f"UI asset {key!r} has an unsafe PNG path: {value!r}")
        return path

    @staticmethod
    def _validated_insets(value: object, key: str = "") -> tuple[int, int, int, int]:
        if isinstance(value, dict):
            names = ("left", "top", "right", "bottom")
            if set(value) != set(names):
                raise ValueError(f"UI asset {key!r} has invalid nine-slice insets")
            values = tuple(value[name] for name in names)
        elif isinstance(value, (list, tuple)) and len(value) == 4:
            values = tuple(value)
        else:
            raise ValueError(f"UI asset {key!r} has invalid nine-slice insets")

        if any(type(inset) is not int or inset < 0 for inset in values):
            raise ValueError(f"UI asset {key!r} has invalid nine-slice insets")
        return values  # type: ignore[return-value]

    def _entry(self, key: object) -> dict[str, Any] | None:
        if not self.available or not isinstance(key, str):
            return None
        assets = self.manifest.get("assets")
        if not isinstance(assets, dict):
            return None
        entry = assets.get(key)
        return entry if isinstance(entry, dict) else None

    def _resource(self, path: PurePosixPath) -> Traversable:
        resource: Traversable = self.root
        for part in path.parts:
            resource = resource.joinpath(part)
        return resource

    @staticmethod
    def _best_effort_convert_alpha(surface: pygame.Surface) -> pygame.Surface:
        try:
            return surface.convert_alpha()
        except (OSError, RuntimeError, pygame.error):
            return surface

    @staticmethod
    def _put_lru(
        cache: OrderedDict[Any, Any], key: Any, value: Any, maximum: int
    ) -> Any:
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > maximum:
            cache.popitem(last=False)
        return value

    def _source_for_path(self, path: PurePosixPath) -> pygame.Surface | None:
        cache_key = path.as_posix()
        if cache_key in self._source_cache:
            cached = self._source_cache[cache_key]
            self._source_cache.move_to_end(cache_key)
            return cached

        self.source_decode_count += 1
        try:
            data = self._resource(path).read_bytes()
            surface = pygame.image.load(io.BytesIO(data), path.name)
            if not isinstance(surface, pygame.Surface):
                raise TypeError("image decoder did not return a Surface")
            surface = self._best_effort_convert_alpha(surface)
        except (OSError, RuntimeError, TypeError, ValueError, pygame.error):
            return self._put_lru(
                self._source_cache,
                cache_key,
                None,
                self.SOURCE_CACHE_LIMIT,
            )

        return self._put_lru(
            self._source_cache,
            cache_key,
            surface,
            self.SOURCE_CACHE_LIMIT,
        )

    def source(self, key: str) -> pygame.Surface | None:
        """Return a decoded full-canvas source image, or ``None`` on failure."""

        entry = self._entry(key)
        if entry is None:
            return None
        try:
            path = self._validated_path(entry.get("path"), key)
        except ValueError:
            return None
        return self._source_for_path(path)

    @staticmethod
    def _validated_size(size: object) -> tuple[int, int] | None:
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            return None
        width, height = size
        if (
            type(width) is not int
            or type(height) is not int
            or width <= 0
            or height <= 0
        ):
            return None
        return width, height

    @staticmethod
    def _cover(source: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        source_width, source_height = source.get_size()
        target_width, target_height = size
        if target_width * source_height >= target_height * source_width:
            scaled_width = target_width
            scaled_height = max(
                target_height,
                round(source_height * target_width / source_width),
            )
        else:
            scaled_height = target_height
            scaled_width = max(
                target_width,
                round(source_width * target_height / source_height),
            )

        scaled = pygame.transform.scale(source, (scaled_width, scaled_height))
        crop = pygame.Rect(
            (scaled_width - target_width) // 2,
            (scaled_height - target_height) // 2,
            target_width,
            target_height,
        )
        return scaled.subsurface(crop).copy()

    @staticmethod
    def _fit_borders(first: int, second: int, available: int) -> tuple[int, int]:
        total = first + second
        if total <= available:
            return first, second
        if total <= 0:
            return 0, 0
        fitted_first = (available * first + total // 2) // total
        fitted_first = max(0, min(available, fitted_first))
        return fitted_first, available - fitted_first

    @staticmethod
    def _blit_slice(
        target: pygame.Surface,
        source: pygame.Surface,
        source_rect: pygame.Rect,
        target_rect: pygame.Rect,
    ) -> None:
        if (
            source_rect.width <= 0
            or source_rect.height <= 0
            or target_rect.width <= 0
            or target_rect.height <= 0
        ):
            return
        region = source.subsurface(source_rect)
        if source_rect.size == target_rect.size:
            target.blit(region, target_rect.topleft)
        else:
            target.blit(
                pygame.transform.scale(region, target_rect.size),
                target_rect.topleft,
            )

    @classmethod
    def _nine_slice(
        cls,
        source: pygame.Surface,
        size: tuple[int, int],
        source_insets: tuple[int, int, int, int],
        target_insets: tuple[int, int, int, int] | None = None,
    ) -> pygame.Surface | None:
        source_width, source_height = source.get_size()
        target_width, target_height = size
        source_left, source_top, source_right, source_bottom = source_insets
        if (
            source_left + source_right > source_width
            or source_top + source_bottom > source_height
        ):
            return None

        target_left, target_top, target_right, target_bottom = (
            target_insets if target_insets is not None else source_insets
        )
        target_left, target_right = cls._fit_borders(
            target_left, target_right, target_width
        )
        target_top, target_bottom = cls._fit_borders(
            target_top, target_bottom, target_height
        )
        source_x = (
            0,
            source_left,
            source_width - source_right,
            source_width,
        )
        source_y = (
            0,
            source_top,
            source_height - source_bottom,
            source_height,
        )
        target_x = (0, target_left, target_width - target_right, target_width)
        target_y = (0, target_top, target_height - target_bottom, target_height)

        result = pygame.Surface(size, flags=pygame.SRCALPHA, depth=32)
        result.fill((0, 0, 0, 0))
        for row in range(3):
            for column in range(3):
                source_rect = pygame.Rect(
                    source_x[column],
                    source_y[row],
                    source_x[column + 1] - source_x[column],
                    source_y[row + 1] - source_y[row],
                )
                target_rect = pygame.Rect(
                    target_x[column],
                    target_y[row],
                    target_x[column + 1] - target_x[column],
                    target_y[row + 1] - target_y[row],
                )
                cls._blit_slice(result, source, source_rect, target_rect)
        return result

    def content_rect(self, key: str, rect: pygame.Rect) -> pygame.Rect | None:
        """Return the authored safe-content area for ``key`` inside ``rect``.

        The result is available only when both the manifest metadata and source
        image are usable. This mirrors :meth:`render`'s per-resource fallback:
        callers can use legacy geometry when one optional sprite is missing.
        Nine-slice content insets shrink with the fitted border slices on tiny
        targets, preventing negative or inverted content rectangles.
        """

        entry = self._entry(key)
        target = pygame.Rect(rect)
        if entry is None or target.width <= 0 or target.height <= 0:
            return None
        try:
            content = self._validated_insets(entry.get("content_insets"), key)
            render_mode = entry.get("render")
            if not isinstance(render_mode, str) or render_mode not in self.RENDER_MODES:
                return None
        except ValueError:
            return None

        source = self.source(key)
        if source is None:
            return None
        source_width, source_height = source.get_size()
        left, top, right, bottom = content

        if render_mode == "nine_slice":
            try:
                source_borders = self._validated_insets(entry.get("insets"), key)
            except ValueError:
                return None
            inset_scale = (
                target.height / max(1, source_height)
                if entry.get("scale_insets_with_height", False)
                else 1.0
            )
            desired_borders = tuple(
                max(0, round(value * inset_scale)) for value in source_borders
            )
            target_left, target_right = self._fit_borders(
                desired_borders[0], desired_borders[2], target.width
            )
            target_top, target_bottom = self._fit_borders(
                desired_borders[1], desired_borders[3], target.height
            )

            def fitted_content(
                value: int,
                desired_border: int,
                target_border: int,
            ) -> int:
                desired_value = max(0, round(value * inset_scale))
                if desired_border <= 0 or target_border >= desired_border:
                    return desired_value
                return round(desired_value * target_border / desired_border)

            left = fitted_content(left, desired_borders[0], target_left)
            right = fitted_content(right, desired_borders[2], target_right)
            top = fitted_content(top, desired_borders[1], target_top)
            bottom = fitted_content(bottom, desired_borders[3], target_bottom)
        else:
            left = round(left * target.width / max(1, source_width))
            right = round(right * target.width / max(1, source_width))
            top = round(top * target.height / max(1, source_height))
            bottom = round(bottom * target.height / max(1, source_height))

        left, right = self._fit_borders(left, right, target.width)
        top, bottom = self._fit_borders(top, bottom, target.height)
        return pygame.Rect(
            target.x + left,
            target.y + top,
            target.width - left - right,
            target.height - top - bottom,
        )

    def render(self, key: str, size: tuple[int, int]) -> pygame.Surface | None:
        """Render an asset at ``size``, returning ``None`` when unavailable."""

        target_size = self._validated_size(size)
        entry = self._entry(key)
        if target_size is None or entry is None:
            return None

        render_mode = entry.get("render")
        if not isinstance(render_mode, str) or render_mode not in self.RENDER_MODES:
            return None
        scale_insets = entry.get("scale_insets_with_height", False) is True
        try:
            path = self._validated_path(entry.get("path"), key)
            insets = (
                self._validated_insets(entry.get("insets"), key)
                if render_mode == "nine_slice"
                else None
            )
        except ValueError:
            return None

        cache_key = (
            key,
            path.as_posix(),
            render_mode,
            insets,
            scale_insets,
            target_size[0],
            target_size[1],
        )
        if cache_key in self._render_cache:
            cached = self._render_cache[cache_key]
            self._render_cache.move_to_end(cache_key)
            return cached

        source = self._source_for_path(path)
        if source is None:
            return None

        self.render_build_count += 1
        try:
            if render_mode == "cover":
                rendered = self._cover(source, target_size)
            elif render_mode == "scale":
                rendered = pygame.transform.scale(source, target_size)
            else:
                assert insets is not None
                inset_scale = target_size[1] / source.get_height()
                target_insets = (
                    (
                        max(0, round(insets[0] * inset_scale)),
                        max(0, round(insets[1] * inset_scale)),
                        max(0, round(insets[2] * inset_scale)),
                        max(0, round(insets[3] * inset_scale)),
                    )
                    if scale_insets
                    else None
                )
                rendered = self._nine_slice(
                    source,
                    target_size,
                    insets,
                    target_insets,
                )
                if rendered is None:
                    return None
            rendered = self._best_effort_convert_alpha(rendered)
            rendered = optimize_immutable_alpha_surface(rendered)
        except (OSError, RuntimeError, TypeError, ValueError, pygame.error):
            return None

        return self._put_lru(
            self._render_cache,
            cache_key,
            rendered,
            self.RENDER_CACHE_LIMIT,
        )

    def clear_derived_caches(self) -> None:
        """Drop rendered-size variants while retaining decoded sources."""

        self._render_cache.clear()

    def clear(self) -> None:
        """Drop decoded, negative, and rendered caches without reloading the manifest."""

        self._source_cache.clear()
        self._render_cache.clear()
