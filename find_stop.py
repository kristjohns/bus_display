#!/usr/bin/env python3
"""Helper script: find an Entur NSR stop ID by name.

Usage:
    python find_stop.py "Vestre Aker Kirke"
    python find_stop.py Blindern
"""

import json
import sys
import urllib.request
import urllib.parse


GEOCODER_URL = "https://api.entur.io/geocoder/v1/autocomplete"


def find_stop(query: str, max_results: int = 8) -> None:
    params = urllib.parse.urlencode({
        "text":  query,
        "lang":  "no",
        "size":  max_results,
        "layers": "venue",
    })
    url = f"{GEOCODER_URL}?{params}"

    req = urllib.request.Request(url, headers={
        "ET-Client-Name": "personal-bus-display-stop-finder"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    features = data.get("features") or []
    if not features:
        print(f"No results for '{query}'")
        return

    print(f"\nResults for '{query}':\n")
    print(f"{'NSR ID':<30}  {'Name':<40}  County")
    print("-" * 80)
    for feat in features:
        props = feat.get("properties") or {}
        nsr_id  = props.get("id", "")
        name    = props.get("name", "")
        county  = props.get("county", "")
        locality = props.get("locality", "")
        label   = f"{name}, {locality}" if locality else name
        print(f"{nsr_id:<30}  {label:<40}  {county}")

    print()
    print("Copy the NSR ID and paste it into STOP_IDS in config.py")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_stop.py <stop name>")
        sys.exit(1)
    find_stop(" ".join(sys.argv[1:]))
