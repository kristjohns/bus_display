"""Map widget: renders an OSM tile map with vehicle markers.

Uses CartoDB Dark Matter tiles for dark theme integration.
Caches tiles to disk in .tile_cache/ directory.
"""

from __future__ import annotations

import io
import logging
import math
import os
from typing import List, Optional, Tuple

import pygame
import requests

import config
from api import VehiclePosition

log = logging.getLogger(__name__)

TILE_SIZE = 256


def _latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    """Convert lat/lon to tile coordinates (floating point) at given zoom."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


class MapWidget:
    """Renders an interactive map with stop location and vehicle markers."""

    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tile_cache")

    def __init__(self, font: pygame.font.Font, font_small: pygame.font.Font):
        self.font = font
        self.font_small = font_small
        self.stop_lat: Optional[float] = None
        self.stop_lon: Optional[float] = None
        self.vehicles: List[VehiclePosition] = []
        self._tiles: dict = {}  # (z, x, y) -> pygame.Surface
        self._tiles_loaded = False

    def set_stop_location(self, lat: float, lon: float) -> None:
        if self.stop_lat != lat or self.stop_lon != lon:
            self.stop_lat = lat
            self.stop_lon = lon
            self._tiles_loaded = False

    def set_vehicles(self, vehicles: List[VehiclePosition]) -> None:
        self.vehicles = vehicles

    def draw(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw the map within the given rectangle."""
        # Load tiles on first draw with known location
        if not self._tiles_loaded and self.stop_lat is not None:
            self._load_tiles(rect)

        # Clip drawing to map area
        old_clip = screen.get_clip()
        screen.set_clip(rect)

        # Dark background
        screen.fill(config.COLOR_MAP_BG, rect)

        if self.stop_lat is not None:
            self._draw_tiles(screen, rect)
            self._draw_vehicles(screen, rect)
            self._draw_stop_marker(screen, rect)
        else:
            msg = self.font.render("Laster kart…", True, config.COLOR_TEXT_DIM)
            screen.blit(msg, (
                rect.centerx - msg.get_width() // 2,
                rect.centery - msg.get_height() // 2,
            ))

        # Border
        pygame.draw.rect(screen, config.COLOR_DIVIDER, rect, 2)

        # "Kart" title in top-left corner
        title = self.font_small.render("Kart", True, config.COLOR_TEXT_DIM)
        screen.blit(title, (rect.x + 10, rect.y + 6))

        # Restore clip
        screen.set_clip(old_clip)

    # -------------------------------------------------------------------
    # Coordinate helpers
    # -------------------------------------------------------------------

    def _latlon_to_pixel(
        self, lat: float, lon: float, rect: pygame.Rect
    ) -> Tuple[int, int]:
        """Convert lat/lon to pixel coordinates within the map rect."""
        cx, cy = _latlon_to_tile(self.stop_lat, self.stop_lon, config.MAP_ZOOM)
        tx, ty = _latlon_to_tile(lat, lon, config.MAP_ZOOM)

        dx = (tx - cx) * TILE_SIZE
        dy = (ty - cy) * TILE_SIZE

        return int(rect.centerx + dx), int(rect.centery + dy)

    # -------------------------------------------------------------------
    # Tile management
    # -------------------------------------------------------------------

    def _load_tiles(self, rect: pygame.Rect) -> None:
        """Download and cache the tiles needed to fill the map area."""
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        cx, cy = _latlon_to_tile(self.stop_lat, self.stop_lon, config.MAP_ZOOM)

        # How many tiles needed in each direction from the center tile
        tiles_x = rect.width // TILE_SIZE // 2 + 2
        tiles_y = rect.height // TILE_SIZE // 2 + 2

        center_tx = int(cx)
        center_ty = int(cy)

        for dx in range(-tiles_x, tiles_x + 1):
            for dy in range(-tiles_y, tiles_y + 1):
                self._fetch_tile(config.MAP_ZOOM, center_tx + dx, center_ty + dy)

        self._tiles_loaded = True
        log.info(
            "Map tiles loaded: %d tiles cached for zoom %d",
            len(self._tiles), config.MAP_ZOOM,
        )

    def _fetch_tile(self, z: int, x: int, y: int) -> None:
        """Fetch a single tile, using disk cache when available."""
        key = (z, x, y)
        if key in self._tiles:
            return

        cache_path = os.path.join(self.CACHE_DIR, f"{z}_{x}_{y}.png")

        # Try disk cache first
        if os.path.exists(cache_path):
            try:
                self._tiles[key] = pygame.image.load(cache_path).convert()
                return
            except pygame.error:
                pass

        # Download from tile server
        url = config.TILE_URL.format(z=z, x=x, y=y)
        try:
            resp = requests.get(url, timeout=10, headers={
                "User-Agent": "personal-bus-display/1.0",
            })
            resp.raise_for_status()

            with open(cache_path, "wb") as f:
                f.write(resp.content)

            self._tiles[key] = pygame.image.load(
                io.BytesIO(resp.content)
            ).convert()
        except Exception as exc:
            log.warning("Failed to fetch tile z=%d x=%d y=%d: %s", z, x, y, exc)

    # -------------------------------------------------------------------
    # Drawing
    # -------------------------------------------------------------------

    def _draw_tiles(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Blit cached tiles onto the screen."""
        cx, cy = _latlon_to_tile(self.stop_lat, self.stop_lon, config.MAP_ZOOM)

        for (z, tx, ty), tile_surf in self._tiles.items():
            if z != config.MAP_ZOOM:
                continue

            px = rect.centerx + (tx - cx) * TILE_SIZE
            py = rect.centery + (ty - cy) * TILE_SIZE

            screen.blit(tile_surf, (int(px), int(py)))

    def _draw_stop_marker(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw a marker at the stop location."""
        sx, sy = self._latlon_to_pixel(self.stop_lat, self.stop_lon, rect)

        # White outer ring + coloured fill
        pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 10, 2)
        pygame.draw.circle(screen, config.COLOR_STOP_MARKER, (sx, sy), 7)

        # "Stoppested" label
        label = self.font_small.render("Stoppested", True, (255, 255, 255))
        # Label background for readability
        bg = pygame.Surface(
            (label.get_width() + 8, label.get_height() + 4), pygame.SRCALPHA
        )
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, (sx + 14, sy - label.get_height() // 2 - 2))
        screen.blit(label, (sx + 18, sy - label.get_height() // 2))

    def _draw_vehicles(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw vehicle markers on the map."""
        for v in self.vehicles:
            vx, vy = self._latlon_to_pixel(v.latitude, v.longitude, rect)

            # Skip vehicles outside the visible map area
            if not rect.collidepoint(vx, vy):
                continue

            # Coloured circle with line number
            pygame.draw.circle(screen, (255, 255, 255), (vx, vy), 16, 2)
            pygame.draw.circle(screen, v.badge_colour, (vx, vy), 14)

            # Line number centred inside the circle
            num_text = self.font_small.render(
                v.line_number, True, v.badge_text_colour
            )
            screen.blit(num_text, (
                vx - num_text.get_width() // 2,
                vy - num_text.get_height() // 2,
            ))

            # Destination label next to the marker
            if v.destination:
                dest_text = self.font_small.render(
                    v.destination, True, (255, 255, 255)
                )
                bg = pygame.Surface(
                    (dest_text.get_width() + 8, dest_text.get_height() + 4),
                    pygame.SRCALPHA,
                )
                bg.fill((0, 0, 0, 160))
                screen.blit(bg, (vx + 20, vy - dest_text.get_height() // 2 - 2))
                screen.blit(dest_text, (
                    vx + 24, vy - dest_text.get_height() // 2
                ))
