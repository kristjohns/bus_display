"""Pygame-based departure board renderer.

Renders a Ruter-style full-screen departure board.
Works identically on desktop (windowed) and Raspberry Pi (fullscreen).
"""

from __future__ import annotations

import datetime
import os
import sys
from typing import List, Optional

import pygame

import config
from api import Departure

# ---------------------------------------------------------------------------
# Display class
# ---------------------------------------------------------------------------

class DepartureBoard:
    """Manages the pygame window and renders the departure board."""

    def __init__(self, fullscreen: bool = False):
        pygame.init()
        pygame.display.set_caption("Avgangstavle")

        flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF if fullscreen \
                else pygame.RESIZABLE

        self.screen = pygame.display.set_mode(
            (config.SCREEN_WIDTH, config.SCREEN_HEIGHT), flags
        )
        self.clock = pygame.time.Clock()

        # Hide cursor in fullscreen
        if fullscreen:
            pygame.mouse.set_visible(False)

        self._load_fonts()
        self.departures: List[Departure] = []
        self.error_message: Optional[str] = None
        self.last_updated: Optional[datetime.datetime] = None

    def _load_fonts(self) -> None:
        # Try to find a nice system font; fall back to pygame default
        candidates = ["dejavusans", "liberationsans", "freesans", "arial", "sans"]
        font_name = pygame.font.match_font(",".join(candidates)) or None

        self.font_large  = pygame.font.Font(font_name, config.FONT_LARGE)
        self.font_medium = pygame.font.Font(font_name, config.FONT_MEDIUM)
        self.font_small  = pygame.font.Font(font_name, config.FONT_SMALL)
        self.font_tiny   = pygame.font.Font(font_name, config.FONT_TINY)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def update_departures(self, departures: List[Departure]) -> None:
        self.departures = departures
        self.last_updated = datetime.datetime.now()
        self.error_message = None

    def set_error(self, message: str) -> None:
        self.error_message = message

    def draw(self) -> None:
        w, h = self.screen.get_size()
        self.screen.fill(config.COLOR_BG)

        y = 0
        y = self._draw_header(y, w)
        y = self._draw_column_headers(y, w)
        y = self._draw_departures(y, w, h)
        self._draw_footer(h, w)

        if self.error_message:
            self._draw_error(w, h)

        pygame.display.flip()
        self.clock.tick(config.FPS)

    def handle_events(self) -> bool:
        """Process events; returns False if the application should quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    return False
                if event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
        return True

    def quit(self) -> None:
        pygame.quit()

    # -----------------------------------------------------------------------
    # Drawing helpers
    # -----------------------------------------------------------------------

    def _draw_header(self, y: int, w: int) -> int:
        """Draw the top header with stop name and clock. Returns new y."""
        header_h = config.FONT_LARGE + 28

        # Background
        pygame.draw.rect(self.screen, config.COLOR_HEADER_BG, (0, y, w, header_h))
        pygame.draw.line(self.screen, config.COLOR_DIVIDER, (0, y + header_h - 1),
                         (w, y + header_h - 1), 2)

        # Stop name (left)
        stop_name = self.departures[0].stop_name if self.departures else "Avgangstavle"
        surf = self.font_large.render(stop_name, True, config.COLOR_TEXT)
        self.screen.blit(surf, (24, y + 14))

        # Clock (right)
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        clock_surf = self.font_large.render(now_str, True, config.COLOR_TEXT)
        self.screen.blit(clock_surf, (w - clock_surf.get_width() - 24, y + 14))

        return y + header_h

    def _draw_column_headers(self, y: int, w: int) -> int:
        col_h = config.FONT_SMALL + 14
        pygame.draw.rect(self.screen, config.COLOR_HEADER_BG, (0, y, w, col_h))
        pygame.draw.line(self.screen, config.COLOR_DIVIDER, (0, y + col_h - 1),
                         (w, y + col_h - 1), 1)

        cols = self._column_positions(w)
        labels = ["Linje", "Destinasjon", "Avgang"]
        for label, x in zip(labels, [cols["line"], cols["dest"], cols["time"]]):
            surf = self.font_small.render(label, True, config.COLOR_TEXT_DIM)
            if label == "Avgang":
                self.screen.blit(surf, (x - surf.get_width(), y + 7))
            else:
                self.screen.blit(surf, (x, y + 7))

        return y + col_h

    def _draw_departures(self, y: int, w: int, h: int) -> int:
        row_h = config.FONT_MEDIUM + 22
        cols   = self._column_positions(w)
        rows   = min(len(self.departures), config.ROWS_ON_SCREEN)

        if not self.departures:
            msg = "Ingen avganger"
            surf = self.font_medium.render(msg, True, config.COLOR_TEXT_DIM)
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, y + 40))
            return y + 80

        for i in range(rows):
            dep = self.departures[i]
            row_color = config.COLOR_ROW_ODD if i % 2 == 0 else config.COLOR_ROW_EVEN
            pygame.draw.rect(self.screen, row_color, (0, y, w, row_h))

            # Subtle divider
            pygame.draw.line(self.screen, config.COLOR_DIVIDER,
                             (0, y + row_h - 1), (w, y + row_h - 1), 1)

            row_y_center = y + row_h // 2

            # Line number badge
            self._draw_line_badge(dep, cols["line"], row_y_center)

            # Destination
            dest_text = dep.destination
            dest_color = config.COLOR_CANCELLED if dep.cancelled else config.COLOR_TEXT
            dest_surf = self.font_medium.render(dest_text, True, dest_color)
            self.screen.blit(dest_surf, (cols["dest"],
                                         row_y_center - dest_surf.get_height() // 2))

            # Real-time indicator dot
            if dep.realtime and not dep.cancelled:
                dot_x = cols["rt_dot"]
                pygame.draw.circle(self.screen, config.COLOR_REALTIME_DOT,
                                   (dot_x, row_y_center), 7)

            # Departure time
            time_str = dep.display_time
            mins = dep.minutes_until
            if dep.cancelled:
                time_color = config.COLOR_CANCELLED
            elif mins <= 1:
                time_color = config.COLOR_TIME_NOW
            elif mins <= 4:
                time_color = config.COLOR_TIME_SOON
            else:
                time_color = config.COLOR_TEXT

            time_surf = self.font_medium.render(time_str, True, time_color)
            time_x = cols["time"] - time_surf.get_width()
            self.screen.blit(time_surf, (time_x,
                                          row_y_center - time_surf.get_height() // 2))

            y += row_h

        return y

    def _draw_line_badge(self, dep: Departure, x: int, cy: int) -> None:
        """Draw coloured pill badge with the line number."""
        text_surf = self.font_medium.render(dep.line_number, True,
                                            dep.badge_text_colour)
        pad_x, pad_y = 18, 8
        rect_w = text_surf.get_width() + pad_x * 2
        rect_h = text_surf.get_height() + pad_y * 2
        rect = pygame.Rect(x, cy - rect_h // 2, rect_w, rect_h)
        pygame.draw.rect(self.screen, dep.badge_colour, rect, border_radius=8)
        self.screen.blit(text_surf, (x + pad_x, cy - text_surf.get_height() // 2))

    def _draw_footer(self, h: int, w: int) -> None:
        footer_h = config.FONT_TINY + 12
        pygame.draw.rect(self.screen, config.COLOR_HEADER_BG,
                         (0, h - footer_h, w, footer_h))
        pygame.draw.line(self.screen, config.COLOR_DIVIDER,
                         (0, h - footer_h), (w, h - footer_h), 1)

        # Last updated
        if self.last_updated:
            ts = self.last_updated.strftime("Oppdatert: %H:%M:%S")
            surf = self.font_tiny.render(ts, True, config.COLOR_TEXT_DIM)
            self.screen.blit(surf, (24, h - footer_h + 6))

        # Data source
        source = "Data: Entur / Ruter  |  Trykk F = fullskjerm  |  Q = avslutt"
        surf = self.font_tiny.render(source, True, config.COLOR_TEXT_DIM)
        self.screen.blit(surf, (w - surf.get_width() - 24, h - footer_h + 6))

    def _draw_error(self, w: int, h: int) -> None:
        overlay = pygame.Surface((w, 60), pygame.SRCALPHA)
        overlay.fill((180, 40, 40, 200))
        self.screen.blit(overlay, (0, h // 2 - 30))
        surf = self.font_small.render(
            f"Feil: {self.error_message}", True, (255, 255, 255)
        )
        self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h // 2 - 15))

    def _column_positions(self, w: int) -> dict:
        """Return x positions for each column."""
        return {
            "line":    24,
            "dest":    180,
            "rt_dot":  w - 340,
            "time":    w - 24,
        }
