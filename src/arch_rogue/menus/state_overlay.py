# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuStateOverlayMixin:
    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        victory = self.g.state == "victory"
        color = (214, 168, 92) if victory else (176, 48, 44)
        title = "Dungeon Cleared" if victory else "You Died"

        # Full-screen colored dimming over the world — blood red for death, gold for victory.
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        if victory:
            overlay.fill((0, 0, 0, 176))
        else:
            overlay.fill((28, 6, 8, 210))
        self.screen.blit(overlay, (0, 0))
        # A faint colored wash to set the mood.
        wash = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(
            wash,
            (*color, 32),
            pygame.Rect(-width // 4, -height // 3, width * 3 // 2, height * 4 // 3),
        )
        self.screen.blit(wash, (0, 0))

        unlock_note = (
            " Hell difficulty is now unlocked in Options."
            if victory and getattr(self.g, "hell_unlocked_this_run", False)
            else ""
        )
        subtitle = (
            f"You survived all {self.dungeon_depth} depths and broke the gate."
            f"{unlock_note}"
            if victory
            else f"The dungeon claims another {self.g.player.class_name}."
        )
        prompt = "Press R or Pause / Back to choose a new run"

        panel_w = min(width - 64, self.u(820))
        panel_h = min(height - 80, self.u(520))
        panel = pygame.Rect(
            (width - panel_w) // 2, (height - panel_h) // 2, panel_w, panel_h
        )
        # Draw the panel on top of the red overlay so text stays readable.
        # Use a neutral accent for the body so the stone panel reads as a distinct
        # surface on top of the red wash, instead of being tinted red itself.
        self.panel(panel, self.IRON, alpha=255)

        inner = panel.inflate(-self.u(54), -self.u(42))

        # Gothic crest ornament above the title, centered.
        crest_y = inner.y + self.u(8) + self.u(14)
        self._draw_state_crest(panel.centerx, crest_y, color, victory)

        # Title, centered.
        title_y = crest_y + self.u(28)
        self.draw_text(
            title,
            self.g.big_font,
            color,
            pygame.Rect(inner.x, title_y, inner.width, self.g.big_font.get_height()),
            align="center",
        )
        # Thin gold rule under the title, centered.
        rule_y = title_y + self.g.big_font.get_height() + self.u(6)
        rule_half = min(inner.width // 2 - self.u(40), self.u(180))
        pygame.draw.line(
            self.screen,
            self.shade(color, -40),
            (panel.centerx - rule_half, rule_y),
            (panel.centerx + rule_half, rule_y),
            max(1, self.u(1)),
        )
        pygame.draw.circle(
            self.screen, color, (panel.centerx, rule_y), max(2, self.u(2))
        )

        # Subtitle, centered.
        sub_y = rule_y + self.u(14)
        sub_h = self.g.font.get_height() + self.u(6)
        self.draw_text(
            subtitle,
            self.g.font,
            self.TEXT,
            pygame.Rect(inner.x, sub_y, inner.width, sub_h),
            align="center",
        )

        # Run-stats table inside a recessed sub-panel.
        table_top = sub_y + sub_h + self.u(14)
        table_bottom = inner.bottom - self.u(34)
        self._draw_run_stats_table(
            pygame.Rect(inner.x, table_top, inner.width, table_bottom - table_top),
            victory,
        )

        # Prompt footer, centered.
        self.draw_text(
            prompt,
            self.g.small_font,
            self.MUTED,
            pygame.Rect(inner.x, inner.bottom - self.u(26), inner.width, self.u(22)),
            align="center",
        )

    def _draw_run_stats_table(self, rect: pygame.Rect, victory: bool) -> None:
        """A clean two-column run-stats table: label (left) · value (right)."""
        rows = self._run_stats_rows(victory)
        if not rows:
            return
        # Recessed sub-panel behind the table — neutral iron border so it reads
        # as a distinct surface, not a red-tinted one.
        pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(6))
        pygame.draw.rect(
            self.screen,
            self.IRON,
            rect,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )

        pad_x = self.u(20)
        pad_y = self.u(12)
        body = rect.inflate(-pad_x * 2, -pad_y * 2)
        label_font = self.g.small_font
        value_font = self.g.small_font
        row_h = max(label_font.get_height() + self.u(8), self.u(22))
        gap = self.u(4)
        # Two columns: label left, value right-aligned.
        label_w = min(self.u(260), body.width // 2)
        value_w = body.width - label_w
        y = body.y
        for label, value in rows:
            if y + row_h > body.bottom:
                break
            row_rect = pygame.Rect(body.x, y, body.width, row_h)
            # Faint separator line between rows.
            if y > body.y:
                pygame.draw.line(
                    self.screen,
                    self.STONE_SHADOW,
                    (row_rect.x, row_rect.y),
                    (row_rect.right, row_rect.y),
                    max(1, self.u(1)),
                )
            self.draw_text(
                label,
                label_font,
                self.MUTED,
                pygame.Rect(row_rect.x, row_rect.y, label_w, row_h),
                valign="center",
            )
            self.draw_text(
                value,
                value_font,
                self.TITLE,
                pygame.Rect(row_rect.right - value_w, row_rect.y, value_w, row_h),
                align="right",
                valign="center",
            )
            y += row_h + gap

    def _run_stats_rows(self, victory: bool) -> list[tuple[str, str]]:
        """Build clean label/value pairs for the run-stats table."""
        g = self.g
        minutes = int(g.elapsed // 60)
        seconds = int(g.elapsed % 60)
        cause = g.run_stats.cause_of_death or ("survived" if victory else "unknown")
        bosses = ", ".join(g.run_stats.defeated_bosses[-3:]) or (
            "Gate defeated" if g.run_stats.boss_killed else "none"
        )
        notable = ", ".join(g.run_stats.notable_loot[-3:]) or "none"
        discoveries = ", ".join(g.run_stats.discoveries[-3:]) or "none"
        progress = g.meta_progress
        return [
            ("Time", f"{minutes:02d}:{seconds:02d}"),
            ("Depth reached", f"{g.current_depth} / {self.dungeon_depth}"),
            ("Difficulty", g.difficulty_profile().name),
            ("Run modifier", g.run_modifier.name),
            ("Class", g.player.class_name),
            ("Kills", str(g.run_stats.kills)),
            ("Boss", "defeated" if g.run_stats.boss_killed else "alive"),
            ("Elites slain", str(g.run_stats.elites_killed)),
            ("Minibosses slain", str(g.run_stats.minibosses_killed)),
            ("Damage taken", str(g.run_stats.damage_taken)),
            ("Cause of death", cause if not victory else "—"),
            ("Loot picked up", str(g.run_stats.loot_picked_up)),
            ("Potions used", str(g.run_stats.potions_used)),
            ("Shrines used", str(g.run_stats.shrines_used)),
            ("Secrets opened", str(g.run_stats.secrets_opened)),
            ("Discoveries", discoveries),
            ("Traps triggered", str(g.run_stats.traps_triggered)),
            ("Challenge rooms", str(g.run_stats.challenge_rooms_cleared)),
            ("Story choices", str(g.run_stats.story_choices)),
            ("Guests met", str(g.run_stats.guests_met)),
            ("Upgrades chosen", str(g.run_stats.upgrades_chosen)),
            ("Notable loot", notable),
            ("Bosses defeated", bosses),
            (
                "Mastery",
                f"best depth {progress.get('best_depth', 0)} · "
                f"clears {progress.get('clears', 0)} · "
                f"known bosses {len(progress.get('bosses_defeated', []))}",
            ),
        ]

    def _draw_state_crest(self, cx: int, cy: int, color: Color, victory: bool) -> None:
        """A small gothic crest: a downward blade for death, a sunburst for victory."""
        r = self.u(14)
        if victory:
            # Sunburst rays.
            for i in range(12):
                angle = i * math.tau / 12
                x1 = cx + int(math.cos(angle) * r * 0.6)
                y1 = cy + int(math.sin(angle) * r * 0.6)
                x2 = cx + int(math.cos(angle) * r * 1.4)
                y2 = cy + int(math.sin(angle) * r * 1.4)
                pygame.draw.line(
                    self.screen,
                    self.shade(color, -20),
                    (x1, y1),
                    (x2, y2),
                    max(1, self.u(2)),
                )
            pygame.draw.circle(self.screen, color, (cx, cy), max(2, r // 2))
            pygame.draw.circle(
                self.screen, self.shade(color, 40), (cx, cy), max(1, r // 4)
            )
        else:
            # Downward blade / broken sword.
            blade = [
                (cx, cy - r),
                (cx + r // 3, cy),
                (cx, cy + r),
                (cx - r // 3, cy),
            ]
            pygame.draw.polygon(self.screen, self.shade(color, -30), blade)
            pygame.draw.polygon(self.screen, color, blade, max(1, self.u(1)))
            # Crossguard.
            pygame.draw.line(
                self.screen,
                self.shade(color, 20),
                (cx - r, cy - r // 2),
                (cx + r, cy - r // 2),
                max(1, self.u(2)),
            )
