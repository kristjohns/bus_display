"""Entur Journey Planner API client.

Fetches real-time departures for a list of NSR stop places and returns
a flat list of Departure dataclass objects, sorted by expected departure time.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import List, Optional

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


# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

_QUERY = """
{{
  stopPlace(id: "{stop_id}") {{
    name
    estimatedCalls(
      numberOfDepartures: {n}
      timeRange: 7200
      omitNonBoarding: true
    ) {{
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      destinationDisplay {{ frontText }}
      serviceJourney {{
        line {{
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
            )
            all_deps.append(dep)

    all_deps.sort(key=lambda d: d.expected_time)
    return all_deps


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
