#!/usr/bin/env python3
"""Debug script: print raw Entur API response for the configured stop."""

import json
import requests

STOP_ID = "NSR:StopPlace:6312"
URL = "https://api.entur.io/journey-planner/v3/graphql"

query = """
{
  stopPlace(id: "%s") {
    name
    estimatedCalls(
      numberOfDepartures: 20
      timeRange: 7200
    ) {
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      destinationDisplay { frontText }
      serviceJourney {
        line {
          publicCode
          transportMode
        }
      }
    }
  }
}
""" % STOP_ID

headers = {
    "Content-Type": "application/json",
    "ET-Client-Name": "personal-bus-display",
}

print(f"Querying: {STOP_ID}")
print(f"URL: {URL}\n")

resp = requests.post(URL, json={"query": query}, headers=headers, timeout=10)
print(f"HTTP status: {resp.status_code}\n")

data = resp.json()
print(json.dumps(data, indent=2, ensure_ascii=False))
