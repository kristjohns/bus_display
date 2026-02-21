#!/usr/bin/env python3
"""Bus departure board – main entry point.

Usage:
    python main.py                  # windowed, live API data
    python main.py --fullscreen     # fullscreen (for Pi / TV)
    python main.py --mock           # windowed, fake data (no internet needed)
    python main.py --fullscreen --mock
"""

import argparse
import logging
import sys
import time

import config
import api
from display import DepartureBoard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ruter departure board")
    p.add_argument("--fullscreen", action="store_true",
                   help="Start in fullscreen mode")
    p.add_argument("--mock", action="store_true",
                   help="Use fake departure data (no API calls)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    fullscreen = args.fullscreen or config.FULLSCREEN

    board = DepartureBoard(fullscreen=fullscreen)

    if args.mock:
        log.info("Mock mode – using fake departure data")
        board.update_departures(api.mock_departures())
        # Set mock stop location (Vestre Aker Kirke)
        board.set_stop_location(59.948, 10.694)
        board.update_routes(api.mock_route_info())

    last_fetch = 0.0
    last_vehicle_fetch = 0.0
    stop_location_set = False

    running = True
    while running:
        running = board.handle_events()

        now = time.monotonic()

        # ------ Departure refresh (every REFRESH_INTERVAL seconds) ------
        if not args.mock and (now - last_fetch) >= config.REFRESH_INTERVAL:
            log.info("Fetching departures from Entur API…")
            try:
                deps = api.fetch_departures(config.STOP_IDS)
                if deps:
                    board.update_departures(deps)
                    log.info("Got %d departures", len(deps))

                    # Set stop location for the map (first time or update)
                    loc = api.get_stop_location()
                    if loc and not stop_location_set:
                        board.set_stop_location(loc[0], loc[1])
                        stop_location_set = True
                        log.info("Stop location set: %.4f, %.4f", loc[0], loc[1])
                else:
                    log.warning("No departures returned")
                    board.set_error("Ingen avganger funnet – sjekk STOP_IDS i config.py")
            except Exception as exc:
                log.error("Fetch failed: %s", exc)
                board.set_error(str(exc))
            last_fetch = now

        # ------ Route + vehicle refresh (every VEHICLE_REFRESH_INTERVAL) ------
        if not args.mock and (now - last_vehicle_fetch) >= config.VEHICLE_REFRESH_INTERVAL:
            loc = api.get_stop_location()
            if loc and board.departures:
                try:
                    vehicles = api.fetch_vehicle_positions(
                        board.departures, loc[0], loc[1], max_vehicles=20
                    )
                    routes = api.fetch_route_info(board.departures, vehicles)
                    board.update_routes(routes)
                    log.info(
                        "Routes: %d shown, %d with live vehicle",
                        len(routes),
                        sum(1 for r in routes if r.vehicle),
                    )
                except Exception as exc:
                    log.error("Route/vehicle fetch failed: %s", exc)
            last_vehicle_fetch = now

        # In mock mode, refresh mock data every 30s so minutes-until stays live
        if args.mock and (now - last_fetch) >= 30:
            board.update_departures(api.mock_departures())
            board.update_routes(api.mock_route_info())
            last_fetch = now

        board.draw()

    board.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
