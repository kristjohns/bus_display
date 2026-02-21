"""Entur Journey Planner API client.

Fetches real-time departures for a list of NSR stop places and returns
a flat list of Departure dataclass objects, sorted by expected departure time.

Also fetches live vehicle positions via the Entur Vehicles v2 GraphQL API.
"""

from __future__ import annotations

import datetime
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Departure:
    stop_name: str
    line_number: str
    destination: str
    aimed_time: datetime.datetime
    expected_time: datetime.datetime
    realtime: bool
    cancelled: bool
    transport_mode: str          # "bus", "tram", "metro", "rail", "water"
    line_colour: str             # hex string e.g. "E60000" (may be empty)
    line_text_colour: str        # hex string e.g. "FFFFFF" (may be empty)
    service_journey_id: str = "" # e.g. "RUT:ServiceJourney:20-123456"
    line_id: str = ""            # e.g. "RUT:Line:20"

    @property
    def minutes_until(self) -> int:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        delta = self.expected_time - now
        return max(0, int(delta.total_seconds() // 60))

    @property
    def display_time(self) -> str:
        mins = self.minutes_until
        if self.cancelled:
            return "avlyst"
        if mins <= 0:
            return "nå"
        if mins < 60:
            return f"{mins} min"
        # Show clock time for departures > 60 min away
        local = self.expected_time.astimezone()
        return local.strftime("%H:%M")

    @property
    def badge_colour(self) -> tuple[int, int, int]:
        """Return (R, G, B) for the line number badge background."""
        if self.line_colour:
            try:
                h = self.line_colour.lstrip("#")
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except (ValueError, IndexError):
                pass
        return config.COLOR_BADGE_DEFAULT

    @property
    def badge_text_colour(self) -> tuple[int, int, int]:
        if self.line_text_colour:
            try:
                h = self.line_text_colour.lstrip("#")
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except (ValueError, IndexError):
                pass
        return (255, 255, 255)


@dataclass
class VehiclePosition:
    latitude: float
    longitude: float
    line_ref: str               # e.g. "RUT:Line:20"
    line_number: str            # public code, e.g. "20"
    service_journey_id: str
    bearing: float              # heading in degrees (0 = north)
    destination: str
    badge_colour: Tuple[int, int, int] = (180, 30, 50)
    badge_text_colour: Tuple[int, int, int] = (255, 255, 255)


# ---------------------------------------------------------------------------
# Stop location storage
# ---------------------------------------------------------------------------

_stop_locations: Dict[str, Tuple[float, float]] = {}


def get_stop_location() -> Optional[Tuple[float, float]]:
    """Return the average (lat, lon) of all fetched stops, or None."""
    if not _stop_locations:
        return None
    lats = [loc[0] for loc in _stop_locations.values()]
    lons = [loc[1] for loc in _stop_locations.values()]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


# ---------------------------------------------------------------------------
# GraphQL query – departures
# ---------------------------------------------------------------------------

_QUERY = """
{{
  stopPlace(id: "{stop_id}") {{
    name
    latitude
    longitude
    estimatedCalls(
      numberOfDepartures: {n}
      timeRange: 7200
    ) {{
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      destinationDisplay {{ frontText }}
      serviceJourney {{
        id
        line {{
          id
          publicCode
          transportMode
          presentation {{ colour textColour }}
        }}
      }}
    }}
  }}
}}
"""


def _parse_dt(s: str) -> datetime.datetime:
    """Parse ISO-8601 datetime string from Entur (ends with +HH:MM or Z)."""
    # Python 3.6 fromisoformat doesn't handle Z or +HH:MM with colon
    s = s.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(s)


def fetch_departures(stop_ids: List[str]) -> List[Departure]:
    """Fetch departures from all stops and return merged, sorted list."""
    all_deps: List[Departure] = []
    headers = {
        "Content-Type": "application/json",
        "ET-Client-Name": config.ENTUR_CLIENT_NAME,
    }

    for stop_id in stop_ids:
        query = _QUERY.format(stop_id=stop_id, n=config.DEPARTURES_PER_STOP)
        try:
            resp = requests.post(
                config.ENTUR_GRAPHQL_URL,
                json={"query": query},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            log.error("API request failed for %s: %s", stop_id, exc)
            continue

        stop_place = (data.get("data") or {}).get("stopPlace")
        if not stop_place:
            log.warning("No stopPlace data returned for %s", stop_id)
            continue

        stop_name: str = stop_place.get("name", stop_id)

        # Store stop coordinates for the map
        stop_lat = stop_place.get("latitude")
        stop_lon = stop_place.get("longitude")
        if stop_lat is not None and stop_lon is not None:
            _stop_locations[stop_id] = (stop_lat, stop_lon)

        calls = stop_place.get("estimatedCalls") or []

        for call in calls:
            sj   = call["serviceJourney"]
            line = sj["line"]
            pres = line.get("presentation") or {}

            line_num = line.get("publicCode") or "?"
            mode     = line.get("transportMode") or "bus"

            # Apply line filter
            if config.LINE_FILTER and line_num not in config.LINE_FILTER:
                continue

            dep = Departure(
                stop_name        = stop_name,
                line_number      = line_num,
                destination      = call["destinationDisplay"]["frontText"],
                aimed_time       = _parse_dt(call["aimedDepartureTime"]),
                expected_time    = _parse_dt(call["expectedDepartureTime"]),
                realtime         = call.get("realtime", False),
                cancelled        = call.get("cancellation", False),
                transport_mode   = mode,
                line_colour      = pres.get("colour") or "",
                line_text_colour = pres.get("textColour") or "",
                service_journey_id = sj.get("id") or "",
                line_id          = line.get("id") or "",
            )
            all_deps.append(dep)

    all_deps.sort(key=lambda d: d.expected_time)
    return all_deps


# ---------------------------------------------------------------------------
# GraphQL query – vehicle positions (Entur Vehicles v2)
# ---------------------------------------------------------------------------

_VEHICLES_QUERY = """
{{
  vehicles(lineRef: "{line_ref}") {{
    bearing
    location {{
      latitude
      longitude
    }}
    line {{
      lineRef
      publicCode
    }}
    serviceJourney {{
      id
    }}
  }}
}}
"""


def fetch_vehicle_positions(
    departures: List[Departure],
    stop_lat: float,
    stop_lon: float,
    max_vehicles: int = 3,
) -> List[VehiclePosition]:
    """Fetch live vehicle positions for the lines in *departures*.

    Returns the *max_vehicles* nearest vehicles to the stop, sorted by
    distance.
    """
    # Collect unique line IDs and a lookup for badge colours
    line_ids: set[str] = set()
    colour_by_line: Dict[str, Tuple[Tuple[int,int,int], Tuple[int,int,int]]] = {}
    dest_by_sj: Dict[str, str] = {}
    for d in departures:
        if d.line_id:
            line_ids.add(d.line_id)
            colour_by_line[d.line_id] = (d.badge_colour, d.badge_text_colour)
        if d.service_journey_id:
            dest_by_sj[d.service_journey_id] = d.destination

    if not line_ids:
        return []

    headers = {
        "Content-Type": "application/json",
        "ET-Client-Name": config.ENTUR_CLIENT_NAME,
    }

    all_vehicles: List[VehiclePosition] = []

    for line_id in line_ids:
        query = _VEHICLES_QUERY.format(line_ref=line_id)
        try:
            resp = requests.post(
                config.ENTUR_VEHICLES_URL,
                json={"query": query},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            log.error("Vehicle positions request failed for %s: %s", line_id, exc)
            continue

        vehicles_data = (data.get("data") or {}).get("vehicles") or []

        for v in vehicles_data:
            loc = v.get("location") or {}
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat is None or lon is None:
                continue

            vline = v.get("line") or {}
            line_ref = vline.get("lineRef") or line_id
            line_number = vline.get("publicCode") or "?"

            sj = v.get("serviceJourney") or {}
            sj_id = sj.get("id") or ""

            badge_col = colour_by_line.get(line_ref, (config.COLOR_BADGE_DEFAULT, (255, 255, 255)))
            destination = dest_by_sj.get(sj_id, "")

            all_vehicles.append(VehiclePosition(
                latitude=lat,
                longitude=lon,
                line_ref=line_ref,
                line_number=line_number,
                service_journey_id=sj_id,
                bearing=v.get("bearing") or 0.0,
                destination=destination,
                badge_colour=badge_col[0],
                badge_text_colour=badge_col[1],
            ))

    # Sort by distance to stop, keep nearest
    def _dist(vp: VehiclePosition) -> float:
        dlat = vp.latitude - stop_lat
        dlon = (vp.longitude - stop_lon) * math.cos(math.radians(stop_lat))
        return dlat * dlat + dlon * dlon

    all_vehicles.sort(key=_dist)
    return all_vehicles[:max_vehicles]


# ---------------------------------------------------------------------------
# Mock data (for offline / unit testing)
# ---------------------------------------------------------------------------

def mock_departures() -> List[Departure]:
    """Return realistic fake departures for Vestre Aker Kirke."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    def _dep(line, dest, mins, rt=True, cancelled=False, colour="E60000"):
        t = now + datetime.timedelta(minutes=mins)
        return Departure(
            stop_name        = "Vestre Aker Kirke",
            line_number      = line,
            destination      = dest,
            aimed_time       = t,
            expected_time    = t,
            realtime         = rt,
            cancelled        = cancelled,
            transport_mode   = "bus",
            line_colour      = colour,
            line_text_colour = "FFFFFF",
            service_journey_id = f"RUT:ServiceJourney:{line}-{mins}",
            line_id          = f"RUT:Line:{line}",
        )

    return [
        _dep("20",  "Skøyen",                      1),
        _dep("28",  "Fornebu",                      3),
        _dep("20",  "Skøyen",                      11),
        _dep("28",  "Fornebu",                     13),
        _dep("20",  "Skøyen",                      21),
        _dep("28",  "Fornebu",                     23, rt=False),
        _dep("20",  "Skøyen",                      31),
        _dep("28",  "Fornebu",                     33, cancelled=True),
    ]


def mock_vehicle_positions() -> List[VehiclePosition]:
    """Return fake vehicle positions near Vestre Aker Kirke (59.948, 10.694)."""
    return [
        VehiclePosition(
            latitude=59.945, longitude=10.700,
            line_ref="RUT:Line:20", line_number="20",
            service_journey_id="RUT:ServiceJourney:20-1",
            bearing=330.0, destination="Skøyen",
            badge_colour=(230, 0, 0), badge_text_colour=(255, 255, 255),
        ),
        VehiclePosition(
            latitude=59.942, longitude=10.710,
            line_ref="RUT:Line:28", line_number="28",
            service_journey_id="RUT:ServiceJourney:28-3",
            bearing=310.0, destination="Fornebu",
            badge_colour=(230, 0, 0), badge_text_colour=(255, 255, 255),
        ),
        VehiclePosition(
            latitude=59.952, longitude=10.685,
            line_ref="RUT:Line:20", line_number="20",
            service_journey_id="RUT:ServiceJourney:20-11",
            bearing=150.0, destination="Skøyen",
            badge_colour=(230, 0, 0), badge_text_colour=(255, 255, 255),
        ),
    ]
