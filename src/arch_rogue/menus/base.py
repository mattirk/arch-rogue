# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
import random
from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuBaseMixin:
    """Shared menu renderer primitives and state.

    The renderer uses a small set of primitives—centered panels, fixed-width key
    badges, wrapped body text, and clipped single-line labels—so every menu uses
    the same alignment rules instead of hand-placed text offsets.

    The visual language is grim and gothic: deep obsidian backgrounds, cold
    stone panels with chiseled bevels, iron corner studs, parchment header
    bands, and a restrained gold/ember accent. All ornament is procedural so the
    look stays crisp at any UI scale.
    """

    # --- Gothic palette -----------------------------------------------------
    # Deep, desaturated obsidian/charcoal base with cold blue undertones.
    BG = (10, 9, 13)
    BG_DEEP = (5, 5, 8)
    PANEL = (20, 18, 24)
    PANEL_2 = (28, 25, 33)
    PANEL_INK = (14, 12, 17)  # recessed inner surface
    STONE_LIGHT = (54, 49, 58)  # bevel highlight
    STONE_SHADOW = (10, 9, 13)  # bevel shadow
    IRON = (74, 70, 82)  # studs / rivets
    IRON_LIGHT = (118, 110, 128)
    IRON_DARK = (32, 30, 38)

    # Text tones — parchment and bone rather than pure white.
    TEXT = (224, 214, 196)
    MUTED = (148, 138, 124)
    TITLE = (236, 214, 168)  # aged gold
    WARNING = (214, 168, 92)  # ember gold
    BLOOD = (152, 38, 40)
    BLOOD_LIGHT = (196, 64, 60)

    # Cached procedural textures (lazily built, keyed by size + scale).
    _stone_cache: dict[tuple[int, int, int], pygame.Surface] = {}

    def __init__(
        self, game: Any, archetypes: Sequence[Archetype], dungeon_depth: int
    ) -> None:
        self.g = game
        self.archetypes = archetypes
        self.dungeon_depth = dungeon_depth

    # --- Accessors ----------------------------------------------------------
    @property
    def screen(self) -> pygame.Surface:
        return self.g.screen

    def u(self, value: int) -> int:
        return self.g.ui(value)

    def shade(self, color: Color, amount: int) -> Color:
        return self.g.shade(color, amount)

    def mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    def accent(self) -> Color:
        return self.g.theme.accent

    # --- Text helpers -------------------------------------------------------
    def ellipsize(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        max_width = max(1, max_width)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        max_width = max(1, max_width)
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = self.ellipsize(word, font, max_width)
        if current:
            lines.append(current)
        return lines or [""]

    def draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        surface = font.render(self.ellipsize(text, font, rect.width), True, color)
        if align == "center":
            x = rect.centerx - surface.get_width() // 2
        elif align == "right":
            x = rect.right - surface.get_width()
        else:
            x = rect.x
        if valign == "center":
            y = rect.centery - surface.get_height() // 2
        elif valign == "bottom":
            y = rect.bottom - surface.get_height()
        else:
            y = rect.y
        self.screen.blit(surface, (x, y))

    def draw_wrapped_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        line_gap: int | None = None,
    ) -> int:
        line_gap = line_gap or max(font.get_height() + 3, self.u(18))
        y = rect.y
        for line in self.wrap_text(text, font, rect.width):
            if y + font.get_height() > rect.bottom:
                return y
            if line:
                self.draw_text(
                    line, font, color, pygame.Rect(rect.x, y, rect.width, line_gap)
                )
            y += line_gap
        return y

    # --- Procedural gothic textures ---------------------------------------
    def _stone_texture(self, w: int, h: int) -> pygame.Surface:
        """A cached, tileable cold-stone noise texture used for backdrops."""
        scale = self.g.ui_scale
        key = (w, h, scale)
        cached = self._stone_cache.get(key)
        if cached is not None:
            return cached
        # Build at a modest resolution then scale up for performance + grit.
        tw, th = max(1, w // (4 * scale) or 1), max(1, h // (4 * scale) or 1)
        surf = pygame.Surface((tw, th))
        surf.fill(self.BG_DEEP)
        rng = random.Random(0xBEEF)
        for _ in range(tw * th // 2):
            x = rng.randint(0, tw - 1)
            y = rng.randint(0, th - 1)
            shade = rng.randint(-10, 14)
            base = surf.get_at((x, y))
            surf.set_at(
                (x, y),
                (
                    max(0, min(255, base[0] + shade)),
                    max(0, min(255, base[1] + shade)),
                    max(0, min(255, base[2] + shade)),
                ),
            )
        # A few hairline cracks for ancient-stone character.
        for _ in range(max(2, th // 24)):
            cx = rng.randint(0, tw - 1)
            cy = rng.randint(0, th - 1)
            length = rng.randint(4, max(5, tw // 3))
            angle = rng.uniform(0, math.tau)
            for i in range(length):
                px = int(cx + math.cos(angle) * i)
                py = int(cy + math.sin(angle) * i)
                if 0 <= px < tw and 0 <= py < th:
                    surf.set_at((px, py), self.STONE_SHADOW)
        scaled = pygame.transform.smoothscale(surf, (w, h))
        self._stone_cache[key] = scaled
        return scaled

    def draw_menu_backdrop(self) -> None:
        width, height = self.screen.get_size()
        accent = self.accent()

        # Base cold-obsidian wash with a faint stone texture for depth.
        self.screen.fill(self.BG_DEEP)
        stone = self._stone_texture(width, height)
        self.screen.blit(stone, (0, 0))

        backdrop = pygame.Surface((width, height), pygame.SRCALPHA)

        # Cold moonlight pools — desaturated, off-center, never bright.
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -96), 30),
            pygame.Rect(-width // 4, -height // 5, width * 3 // 4, height * 3 // 4),
        )
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -120), 24),
            pygame.Rect(width // 2, height // 8, width * 2 // 3, height * 2 // 3),
        )

        # Faint gothic arch silhouettes — three nested arches framing the title.
        arch_color = (*self.shade(accent, -128), 22)
        arch_w = max(self.u(120), width // 6)
        arch_h = max(self.u(220), height * 2 // 5)
        arch_cx = width // 2
        arch_cy = int(height * 0.34)
        for i, scale in enumerate((1.0, 0.78, 0.56)):
            w = int(arch_w * scale)
            h = int(arch_h * scale)
            rect = pygame.Rect(arch_cx - w // 2, arch_cy - h // 2, w, h)
            points = self._arch_points(rect, shoulder=0.62)
            pygame.draw.polygon(backdrop, arch_color, points)
            pygame.draw.lines(
                backdrop,
                (*self.shade(accent, -90), 40),
                True,
                points,
                max(1, self.u(1)),
            )

        # Distant diamond sigils — occult, very faint.
        diamond_color = (*self.shade(accent, -118), 22)
        for center_x, center_y, size in (
            (width // 5, height * 3 // 5, max(70, width // 9)),
            (width * 4 // 5, height * 7 // 12, max(90, width // 8)),
            (width // 2, height * 4 // 5, max(120, width // 6)),
        ):
            points = [
                (center_x, center_y - size // 2),
                (center_x + size, center_y),
                (center_x, center_y + size // 2),
                (center_x - size, center_y),
            ]
            pygame.draw.polygon(backdrop, diamond_color, points)
            pygame.draw.lines(
                backdrop,
                (*self.shade(accent, -80), 36),
                True,
                points,
                max(1, self.u(1)),
            )

        # Bottom vignette — sink the foreground into shadow.
        pygame.draw.ellipse(
            backdrop,
            (0, 0, 0, 96),
            pygame.Rect(-width // 5, height * 2 // 3, width * 7 // 5, height // 2),
        )

        self.screen.blit(backdrop, (0, 0))
        self._draw_edge_vignette()

    def _draw_edge_vignette(self) -> None:
        width, height = self.screen.get_size()
        vignette = pygame.Surface((width, height), pygame.SRCALPHA)
        steps = 6
        for i in range(steps):
            alpha = int(8 + i * 10)
            inset = i * max(2, self.u(6))
            if inset * 2 >= width or inset * 2 >= height:
                break
            pygame.draw.rect(
                vignette,
                (0, 0, 0, alpha),
                vignette.get_rect().inflate(-inset * 2, -inset * 2),
                max(1, self.u(2)),
                border_radius=self.u(6),
            )
        self.screen.blit(vignette, (0, 0))

    def _arch_points(
        self, rect: pygame.Rect, shoulder: float = 0.6, segments: int = 18
    ) -> list[tuple[int, int]]:
        """Return a closed gothic-arch outline (rectangle with a rounded top)."""
        shoulder = max(0.1, min(0.95, shoulder))
        top_y = rect.y
        shoulder_y = rect.y + int(rect.height * shoulder)
        bottom_y = rect.bottom
        left_x = rect.x
        right_x = rect.right
        points: list[tuple[int, int]] = [(left_x, bottom_y), (left_x, shoulder_y)]
        cx = rect.centerx
        rx = max(1, rect.width // 2)
        ry = max(1, shoulder_y - top_y)
        for i in range(segments + 1):
            t = i / segments
            angle = math.pi + t * math.pi  # pi -> 2pi sweeps the top arc
            px = cx + int(math.cos(angle) * rx)
            py = shoulder_y + int(math.sin(angle) * ry)
            points.append((px, py))
        points.append((right_x, shoulder_y))
        points.append((right_x, bottom_y))
        return points

    # --- Ornate panel primitive -------------------------------------------
    def panel(
        self, rect: pygame.Rect, accent: Color | None = None, alpha: int = 245
    ) -> None:
        """Draw a chiseled stone panel with iron studs and a gold inner trim."""
        accent = accent or self.accent()
        radius = self.u(10)

        # Drop shadow — soft, offset down-right.
        shadow = rect.move(max(2, self.u(3)), max(3, self.u(5)))
        shadow_surf = pygame.Surface(shadow.size, pygame.SRCALPHA)
        pygame.draw.rect(
            shadow_surf, (0, 0, 0, 150), shadow_surf.get_rect(), border_radius=radius
        )
        self.screen.blit(shadow_surf, shadow)

        # Body — recessed stone with a subtle vertical gradient.
        if alpha < 255:
            body = pygame.Surface(rect.size, pygame.SRCALPHA)
            self._fill_stone_gradient(body, accent, alpha)
            self.screen.blit(body, rect)
        else:
            self._fill_stone_gradient(self.screen.subsurface(rect), accent, 255)

        # Outer bevel — dark rim then light rim, gives a chiseled edge.
        pygame.draw.rect(
            self.screen,
            self.STONE_SHADOW,
            rect,
            max(1, self.u(2)),
            border_radius=radius,
        )
        inner_bevel = rect.inflate(-self.u(2), -self.u(2))
        pygame.draw.rect(
            self.screen,
            self.STONE_LIGHT,
            inner_bevel,
            max(1, self.u(1)),
            border_radius=max(1, radius - self.u(1)),
        )

        # Gold inner trim — the gothic accent line.
        trim = inner_bevel.inflate(-self.u(4), -self.u(4))
        pygame.draw.rect(
            self.screen,
            self.shade(accent, -32),
            trim,
            max(1, self.u(1)),
            border_radius=max(1, radius - self.u(2)),
        )

        # Iron corner studs — four rivets framing the panel.
        stud_r = max(2, self.u(3))
        inset = self.u(8)
        for corner in (
            (rect.x + inset, rect.y + inset),
            (rect.right - inset, rect.y + inset),
            (rect.x + inset, rect.bottom - inset),
            (rect.right - inset, rect.bottom - inset),
        ):
            pygame.draw.circle(self.screen, self.IRON_DARK, corner, stud_r + 1)
            pygame.draw.circle(self.screen, self.IRON, corner, stud_r)
            pygame.draw.circle(
                self.screen,
                self.IRON_LIGHT,
                (corner[0] - 1, corner[1] - 1),
                max(1, stud_r - 1),
            )

    def _fill_stone_gradient(
        self, surface: pygame.Surface, accent: Color, alpha: int
    ) -> None:
        """Vertical gradient from a slightly lit top to a deep recessed bottom."""
        w, h = surface.get_size()
        if w <= 0 or h <= 0:
            return
        top = self.mix(self.PANEL, accent, 0.06)
        bottom = self.PANEL_INK
        # Draw a few horizontal bands for a smooth-enough gradient without
        # per-pixel work; cheap and reads as cold stone.
        bands = max(8, min(48, h))
        for i in range(bands):
            t = i / max(1, bands - 1)
            color = (
                int(top[0] * (1 - t) + bottom[0] * t),
                int(top[1] * (1 - t) + bottom[1] * t),
                int(top[2] * (1 - t) + bottom[2] * t),
                alpha,
            )
            y = int(i * h / bands)
            y2 = int((i + 1) * h / bands)
            pygame.draw.rect(surface, color, pygame.Rect(0, y, w, y2 - y + 1))

    # --- Menu frame --------------------------------------------------------
    def menu_frame(
        self, title: str, subtitle: str = ""
    ) -> tuple[pygame.Rect, pygame.Rect]:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        title_font = self.g.title_font if height >= self.u(360) else self.g.big_font
        subtitle_font = self.g.small_font
        side_margin = max(self.u(24), 32)
        title_y = max(self.u(30), int(height * 0.12))

        # Ornamental flourish around the title — thin gold rule with center crest.
        self._draw_title_ornament(
            title_y, title_font.get_height(), accent=self.accent()
        )

        self.draw_text(
            title,
            title_font,
            self.TITLE,
            pygame.Rect(
                side_margin,
                title_y - title_font.get_height() // 2,
                width - side_margin * 2,
                title_font.get_height(),
            ),
            align="center",
            valign="center",
        )
        if subtitle:
            self.draw_text(
                subtitle,
                subtitle_font,
                self.MUTED,
                pygame.Rect(
                    side_margin,
                    title_y + title_font.get_height() // 2 + self.u(8),
                    width - side_margin * 2,
                    subtitle_font.get_height(),
                ),
                align="center",
            )

        top = title_y + title_font.get_height() // 2 + self.u(72)
        footer_space = max(self.g.small_font.get_height() + self.u(18), self.u(42))
        panel_w = min(width - side_margin * 2, self.u(860))
        rect = pygame.Rect(
            (width - panel_w) // 2,
            top,
            panel_w,
            max(self.u(110), height - top - footer_space - self.u(10)),
        )
        self.panel(rect)
        self._draw_parchment_header(rect, title)
        content_pad_x = max(self.u(22), 28)
        content_pad_y = max(self.u(20), 24)
        content = rect.inflate(-content_pad_x * 2, -content_pad_y * 2)
        content.y += self.u(8)
        content.h -= self.u(4)
        return rect, content

    def _draw_title_ornament(self, title_y: int, title_h: int, accent: Color) -> None:
        width, _height = self.screen.get_size()
        cx = width // 2
        rule_y = title_y + title_h // 2 + self.u(18)
        half_w = min(width // 2 - self.u(40), self.u(280))
        if half_w <= self.u(20):
            return
        gold = self.shade(accent, 8)
        gold_dim = self.shade(accent, -90)
        # Two thin rules with a gap, dimming toward the edges.
        for offset in (self.u(2), 0):
            pygame.draw.line(
                self.screen,
                gold_dim if offset else gold,
                (cx - half_w, rule_y + offset),
                (cx - self.u(18), rule_y + offset),
                max(1, self.u(1)),
            )
            pygame.draw.line(
                self.screen,
                gold_dim if offset else gold,
                (cx + self.u(18), rule_y + offset),
                (cx + half_w, rule_y + offset),
                max(1, self.u(1)),
            )
        # Center diamond crest.
        crest_r = self.u(5)
        crest = [
            (cx, rule_y - crest_r),
            (cx + crest_r, rule_y),
            (cx, rule_y + crest_r),
            (cx - crest_r, rule_y),
        ]
        pygame.draw.polygon(self.screen, gold, crest)
        pygame.draw.polygon(
            self.screen, self.shade(accent, -40), crest, max(1, self.u(1))
        )
        pygame.draw.circle(self.screen, self.BG_DEEP, (cx, rule_y), max(1, self.u(1)))

    def _draw_parchment_header(self, rect: pygame.Rect, title: str) -> None:
        """A thin aged-parchment band across the top of a panel, with a gold rule."""
        band_h = self.u(6)
        band = pygame.Rect(
            rect.x + self.u(6), rect.y + self.u(6), rect.width - self.u(12), band_h
        )
        parchment = pygame.Surface(band.size, pygame.SRCALPHA)
        parchment.fill((214, 196, 150, 28))
        self.screen.blit(parchment, band)
        pygame.draw.line(
            self.screen,
            self.shade(self.accent(), 18),
            (band.x, band.bottom),
            (band.right, band.bottom),
            max(1, self.u(1)),
        )

    def draw_footer(self, panel: pygame.Rect, text: str) -> None:
        width, height = self.screen.get_size()
        margin = max(self.u(18), 28)
        rect = pygame.Rect(
            margin,
            min(
                height - self.g.small_font.get_height() - self.u(10),
                panel.bottom + self.u(14),
            ),
            width - margin * 2,
            self.g.small_font.get_height() + self.u(4),
        )
        self.draw_text(text, self.g.small_font, self.MUTED, rect, align="center")

    def draw_menu_rows(
        self,
        rows: Sequence[MenuRow],
        rect: pygame.Rect,
        selected_index: int = -1,
    ) -> None:
        key_w = min(max(self.u(108), 108), max(self.u(96), rect.width // 3))
        row_count = max(1, len(rows))
        base_gap = max(self.u(7), 7)
        base_row_h = max(self.g.font.get_height() + self.u(18), self.u(44))
        available_h = max(1, rect.height)
        if row_count * base_row_h + (row_count - 1) * base_gap > available_h:
            gap = max(1, min(base_gap, self.u(3)))
            row_h = max(
                self.g.font.get_height() + self.u(8),
                (available_h - gap * (row_count - 1)) // row_count,
            )
        else:
            row_h = base_row_h
            gap = base_gap
        y = rect.y
        accent = self.accent()
        for index, (key, label, value) in enumerate(rows):
            if y + row_h > rect.bottom:
                break
            row_rect = pygame.Rect(rect.x, y, rect.width, row_h)
            is_selected = index == selected_index
            # Recessed row plate with a faint top highlight.
            plate_fill = self.shade(accent, -100) if is_selected else self.PANEL_INK
            pygame.draw.rect(self.screen, plate_fill, row_rect, border_radius=self.u(5))
            if is_selected:
                glow = pygame.Surface(row_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*accent, 32),
                    glow.get_rect(),
                    border_radius=self.u(5),
                )
                self.screen.blit(glow, row_rect)
            border_color = accent if is_selected else self.PANEL_2
            pygame.draw.rect(
                self.screen,
                border_color,
                row_rect,
                max(1, self.u(1)),
                border_radius=self.u(5),
            )
            pygame.draw.line(
                self.screen,
                self.STONE_LIGHT,
                (row_rect.x + self.u(6), row_rect.y + self.u(1)),
                (row_rect.right - self.u(6), row_rect.y + self.u(1)),
                max(1, self.u(1)),
            )
            if is_selected:
                strip = pygame.Rect(
                    row_rect.x, row_rect.y + self.u(4), self.u(4), row_h - self.u(8)
                )
                pygame.draw.rect(self.screen, accent, strip, border_radius=self.u(3))
                pygame.draw.rect(
                    self.screen,
                    self.shade(accent, 40),
                    strip,
                    border_radius=self.u(3),
                )

            # Key badge — iron plate with gold trim.
            key_rect = pygame.Rect(
                row_rect.x + self.u(8),
                row_rect.y + self.u(7),
                key_w - self.u(16),
                row_h - self.u(14),
            )
            pygame.draw.rect(
                self.screen, self.IRON_DARK, key_rect, border_radius=self.u(4)
            )
            pygame.draw.rect(
                self.screen,
                self.IRON,
                key_rect.inflate(-self.u(2), -self.u(2)),
                border_radius=self.u(3),
            )
            pygame.draw.rect(
                self.screen,
                self.shade(self.accent(), -40),
                key_rect,
                max(1, self.u(1)),
                border_radius=self.u(4),
            )
            self.draw_text(
                key,
                self.g.small_font,
                self.TITLE,
                key_rect.inflate(-self.u(8), 0),
                align="center",
                valign="center",
            )

            value_w = (
                min(rect.width // 4, self.g.small_font.size(value)[0] + self.u(18))
                if value
                else 0
            )
            label_rect = pygame.Rect(
                row_rect.x + key_w + self.u(12),
                row_rect.y,
                row_rect.width - key_w - value_w - self.u(24),
                row_h,
            )
            self.draw_text(label, self.g.font, self.TEXT, label_rect, valign="center")
            if value:
                value_rect = pygame.Rect(
                    row_rect.right - value_w - self.u(10), row_rect.y, value_w, row_h
                )
                self.draw_text(
                    value,
                    self.g.small_font,
                    self.WARNING,
                    value_rect,
                    align="right",
                    valign="center",
                )
            y += row_h + gap
