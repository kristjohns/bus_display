"""Map widget: renders an OSM tile map with route polylines and vehicle markers.

Uses CartoDB Dark Matter tiles for dark theme integration.
Caches tiles to disk in .tile_cache/ directory.

Visual features:
  - Pulsing concentric rings around the stop marker
  - Animated flowing dashes along route polylines
  - Smooth vehicle position interpolation between updates
  - Coloured glow halos behind each live vehicle
  - Destination labels next to vehicles
  - Line legend panel showing active routes and live status
"""

from __future__ import annotations

import io
import logging
import math
import os
import time
from typing import Dict, List, Optional, Tuple

import pygame
import requests

import config
from api import RouteInfo

log = logging.getLogger(__name__)

TILE_SIZE = 256


def _latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    """Convert lat/lon to tile coordinates (floating point) at given zoom."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b, clamped to [a, b]."""
    t = max(0.0, min(1.0, t))
    return a + (b - a) * t


class MapWidget:
    """Renders a map with route polylines, stop dots, and vehicle markers."""

    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tile_cache")

    def __init__(self, font: pygame.font.Font, font_small: pygame.font.Font):
        self.font = font
        self.font_small = font_small
        self.stop_lat: Optional[float] = None
        self.stop_lon: Optional[float] = None
        self.routes: List[RouteInfo] = []
        self._tiles: dict = {}  # (z, x, y) -> pygame.Surface
        self._tiles_loaded = False

        # Animation clock
        self._anim_start = time.monotonic()

        # Vehicle interpolation state
        self._prev_vehicles: Dict[str, Tuple[float, float]] = {}
        self._target_vehicles: Dict[str, Tuple[float, float]] = {}
        self._vehicle_update_time: float = 0.0

    def set_stop_location(self, lat: float, lon: float) -> None:
        if self.stop_lat != lat or self.stop_lon != lon:
            self.stop_lat = lat
            self.stop_lon = lon
            self._tiles_loaded = False

    def set_routes(self, routes: List[RouteInfo]) -> None:
        # Snapshot previous positions for interpolation
        self._prev_vehicles = dict(self._target_vehicles)
        self._target_vehicles = {}
        for r in routes:
            if r.vehicle:
                key = r.vehicle.service_journey_id or r.vehicle.line_ref
                self._target_vehicles[key] = (r.vehicle.latitude, r.vehicle.longitude)
        self._vehicle_update_time = time.monotonic()
        self.routes = routes

    def draw(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw the map within the given rectangle."""
        if not self._tiles_loaded and self.stop_lat is not None:
            self._load_tiles(rect)

        old_clip = screen.get_clip()
        screen.set_clip(rect)

        screen.fill(config.COLOR_MAP_BG, rect)

        if self.stop_lat is not None:
            self._draw_tiles(screen, rect)
            self._draw_routes(screen, rect)
            self._draw_stop_marker(screen, rect)
            self._draw_legend(screen, rect)
        else:
            msg = self.font.render("Laster kart\u2026", True, config.COLOR_TEXT_DIM)
            screen.blit(msg, (
                rect.centerx - msg.get_width() // 2,
                rect.centery - msg.get_height() // 2,
            ))

        pygame.draw.rect(screen, config.COLOR_DIVIDER, rect, 2)

        title = self.font_small.render("Kart", True, config.COLOR_TEXT_DIM)
        screen.blit(title, (rect.x + 10, rect.y + 6))

        screen.set_clip(old_clip)

    # -------------------------------------------------------------------
    # Coordinate helpers
    # -------------------------------------------------------------------

    def _latlon_to_pixel(
        self, lat: float, lon: float, rect: pygame.Rect
    ) -> Tuple[int, int]:
        """Convert lat/lon to absolute pixel coordinates on screen."""
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

        if os.path.exists(cache_path):
            try:
                self._tiles[key] = pygame.image.load(cache_path).convert()
                return
            except pygame.error:
                pass

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
        """Draw a pulsing marker at the queried stop location."""
        sx, sy = self._latlon_to_pixel(self.stop_lat, self.stop_lon, rect)
        t = time.monotonic() - self._anim_start

        # Pulsing concentric rings expanding outward
        for i in range(3):
            phase = (t * 0.7 + i * 0.33) % 1.0
            radius = int(12 + phase * 45)
            alpha = int(160 * (1.0 - phase))
            if alpha > 0:
                ring_surf = pygame.Surface(
                    (radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA
                )
                col = config.COLOR_STOP_MARKER
                pygame.draw.circle(
                    ring_surf, (*col, alpha),
                    (radius + 2, radius + 2), radius, 2,
                )
                screen.blit(ring_surf, (sx - radius - 2, sy - radius - 2))

        # Solid core marker
        pygame.draw.circle(screen, (255, 255, 255), (sx, sy), 10, 2)
        pygame.draw.circle(screen, config.COLOR_STOP_MARKER, (sx, sy), 7)

        # Label
        label = self.font_small.render("Stoppested", True, (255, 255, 255))
        bg = pygame.Surface(
            (label.get_width() + 8, label.get_height() + 4), pygame.SRCALPHA
        )
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, (sx + 14, sy - label.get_height() // 2 - 2))
        screen.blit(label, (sx + 18, sy - label.get_height() // 2))

    def _draw_routes(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw route polylines with animated dashes, stop dots, and
        vehicle markers with glow and destination labels."""
        t = time.monotonic() - self._anim_start

        # Interpolation progress (0..1 between vehicle updates)
        elapsed = time.monotonic() - self._vehicle_update_time
        interp_t = min(1.0, elapsed / max(config.VEHICLE_REFRESH_INTERVAL, 1))

        # --- Route lines and stop dots (translucent overlay) ---
        route_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        for route in self.routes:
            col = route.badge_colour

            # Convert route stops to surface-relative pixel coordinates
            pixels = []
            for lat, lon in route.stops:
                px, py = self._latlon_to_pixel(lat, lon, rect)
                pixels.append((px - rect.x, py - rect.y))

            # Subtle base line
            if len(pixels) >= 2:
                pygame.draw.lines(route_surf, (*col, 70), False, pixels, 3)

            # Animated flowing dashes on top
            if len(pixels) >= 2:
                self._draw_animated_dashes(route_surf, pixels, col, t)

            # Small dot at each stop
            for sx, sy in pixels:
                if -10 <= sx < rect.width + 10 and -10 <= sy < rect.height + 10:
                    pygame.draw.circle(
                        route_surf, (255, 255, 255, 210), (sx, sy), 4
                    )
                    pygame.draw.circle(route_surf, (*col, 255), (sx, sy), 3)

        screen.blit(route_surf, (rect.x, rect.y))

        # --- Vehicle markers (fully opaque, on top) ---
        for route in self.routes:
            if not route.vehicle:
                continue
            v = route.vehicle

            # Interpolate position for smooth movement
            key = v.service_journey_id or v.line_ref
            if key in self._prev_vehicles and key in self._target_vehicles:
                prev_lat, prev_lon = self._prev_vehicles[key]
                tgt_lat, tgt_lon = self._target_vehicles[key]
                lat = _lerp(prev_lat, tgt_lat, interp_t)
                lon = _lerp(prev_lon, tgt_lon, interp_t)
            else:
                lat, lon = v.latitude, v.longitude

            vx, vy = self._latlon_to_pixel(lat, lon, rect)
            if not rect.collidepoint(vx, vy):
                continue

            # Coloured glow halo
            glow_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
            for r in range(30, 8, -3):
                alpha = int(50 * (1.0 - r / 30.0))
                pygame.draw.circle(
                    glow_surf, (*v.badge_colour, alpha), (40, 40), r
                )
            screen.blit(glow_surf, (vx - 40, vy - 40))

            # White-bordered circle body
            pygame.draw.circle(screen, (255, 255, 255), (vx, vy), 18)
            pygame.draw.circle(screen, v.badge_colour, (vx, vy), 16)

            # Direction arrow (triangle pointing in bearing direction)
            br = math.radians(v.bearing)
            tip = (
                vx + int(math.sin(br) * 26),
                vy - int(math.cos(br) * 26),
            )
            perp = math.radians(v.bearing + 90)
            base1 = (
                vx + int(math.sin(perp) * 7),
                vy - int(math.cos(perp) * 7),
            )
            base2 = (
                vx - int(math.sin(perp) * 7),
                vy + int(math.cos(perp) * 7),
            )
            pygame.draw.polygon(screen, (255, 255, 255), [tip, base1, base2])
            pygame.draw.polygon(screen, v.badge_colour, [tip, base1, base2])

            # Line number centred in the circle
            num_text = self.font_small.render(
                v.line_number, True, v.badge_text_colour
            )
            screen.blit(num_text, (
                vx - num_text.get_width() // 2,
                vy - num_text.get_height() // 2,
            ))

            # Destination label next to vehicle
            if v.destination:
                self._draw_vehicle_label(screen, vx, vy, v.destination)

    def _draw_vehicle_label(
        self, screen: pygame.Surface, vx: int, vy: int, text: str
    ) -> None:
        """Draw a labelled tooltip next to a vehicle marker."""
        label = self.font_small.render(text, True, (255, 255, 255))
        lw = label.get_width() + 10
        lh = label.get_height() + 6
        lx = vx + 22
        ly = vy - lh // 2

        # Background pill
        bg = pygame.Surface((lw, lh), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 180))
        pygame.draw.rect(bg, (255, 255, 255, 40), (0, 0, lw, lh), 1,
                         border_radius=4)
        screen.blit(bg, (lx, ly))
        screen.blit(label, (lx + 5, ly + 3))

    def _draw_animated_dashes(
        self,
        surface: pygame.Surface,
        pixels: List[Tuple[int, int]],
        colour: Tuple[int, int, int],
        t: float,
    ) -> None:
        """Draw animated flowing dashes along a polyline.

        Dashes travel along the route in the direction of increasing stop
        index (i.e. the travel direction of the bus).
        """
        dash_on = 18
        dash_off = 14
        cycle = dash_on + dash_off
        speed = 55.0  # px/s
        global_offset = (t * speed) % cycle

        cum_dist = 0.0
        for i in range(1, len(pixels)):
            x0, y0 = pixels[i - 1]
            x1, y1 = pixels[i]
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len < 1:
                cum_dist += seg_len
                continue

            dx = (x1 - x0) / seg_len
            dy = (y1 - y0) / seg_len

            # Walk along this segment, drawing dashes
            p = 0.0
            while p < seg_len:
                phase = (cum_dist + p + global_offset) % cycle
                if phase < dash_on:
                    # Inside a dash – draw to end of this dash or segment
                    remaining = dash_on - phase
                    end_p = min(p + remaining, seg_len)
                    sx = int(x0 + dx * p)
                    sy = int(y0 + dy * p)
                    ex = int(x0 + dx * end_p)
                    ey = int(y0 + dy * end_p)
                    if abs(sx - ex) + abs(sy - ey) > 1:
                        pygame.draw.line(
                            surface, (*colour, 200), (sx, sy), (ex, ey), 3
                        )
                    p = end_p + 0.5
                else:
                    # Inside a gap – skip forward
                    remaining = cycle - phase
                    p += remaining + 0.5

            cum_dist += seg_len

    def _draw_legend(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw a compact legend panel showing active routes and live status."""
        if not self.routes:
            return

        padding = 8
        line_h = self.font_small.get_height() + 6
        legend_h = padding * 2 + len(self.routes) * line_h
        legend_w = 180
        lx = rect.right - legend_w - 10
        ly = rect.y + 30

        # Semi-transparent background
        bg = pygame.Surface((legend_w, legend_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, (lx, ly))

        for i, route in enumerate(self.routes):
            y = ly + padding + i * line_h

            # Colour badge
            badge_w = max(28, self.font_small.size(route.line_number)[0] + 10)
            badge_rect = pygame.Rect(lx + padding, y, badge_w, line_h - 4)
            pygame.draw.rect(
                screen, route.badge_colour, badge_rect, border_radius=4
            )

            # Line number in badge
            num = self.font_small.render(
                route.line_number, True, route.badge_text_colour
            )
            screen.blit(num, (
                badge_rect.centerx - num.get_width() // 2,
                badge_rect.centery - num.get_height() // 2,
            ))

            # Live / route status
            if route.vehicle:
                status_text = "LIVE"
                status_col = (100, 230, 100)
            else:
                status_text = "rute"
                status_col = config.COLOR_TEXT_DIM
            s = self.font_small.render(status_text, True, status_col)
            screen.blit(s, (lx + padding + badge_w + 8, y + 1))

        # Subtle border
        pygame.draw.rect(
            screen, config.COLOR_DIVIDER,
            (lx, ly, legend_w, legend_h), 1, border_radius=4,
        )
