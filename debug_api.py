#!/usr/bin/env python3
"""Debug script: print raw Entur API response for the configured stop."""

import json
import requests
import config

query = """
{{
  stopPlace(id: "{stop_id}") {{
    name
    estimatedCalls(
      numberOfDepartures: 20
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
        }}
      }}
    }}
  }}
}}
""".format(stop_id=config.STOP_IDS[0])

headers = {
    "Content-Type": "application/json",
    "ET-Client-Name": config.ENTUR_CLIENT_NAME,
}

print(f"Querying: {config.STOP_IDS[0]}")
print(f"URL: {config.ENTUR_GRAPHQL_URL}\n")

resp = requests.post(config.ENTUR_GRAPHQL_URL, json={"query": query}, headers=headers, timeout=10)
print(f"HTTP status: {resp.status_code}\n")

data = resp.json()
print(json.dumps(data, indent=2, ensure_ascii=False))
