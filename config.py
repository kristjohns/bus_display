# ---------------------------------------------------------------------------
# Configuration – edit this file to customise your display
# ---------------------------------------------------------------------------

# Stop IDs to show (NSR:StopPlace:XXXXX).
# Run `python find_stop.py "Vestre Aker Kirke"` to discover the correct ID.
STOP_IDS = [
    "NSR:StopPlace:6013",   # placeholder – replace after running find_stop.py
]

# Only show these line numbers.  Empty list = show everything.
LINE_FILTER = []  # empty = show all lines

# How many departures to fetch per stop from the API
DEPARTURES_PER_STOP = 12

# How many rows to display on screen at once
ROWS_ON_SCREEN = 8

# Seconds between API refreshes (Entur recommends ≥ 45 s)
REFRESH_INTERVAL = 45

# ---- Display -----------------------------------------------------------
SCREEN_WIDTH  = 1920
SCREEN_HEIGHT = 1080
FULLSCREEN    = False   # set True on the Pi (or pass --fullscreen flag)
FPS           = 10      # screen refresh rate

# ---- Colours (RGB) -----------------------------------------------------
COLOR_BG           = (10,  18,  40)   # deep navy
COLOR_HEADER_BG    = (20,  30,  60)
COLOR_ROW_ODD      = (16,  24,  50)
COLOR_ROW_EVEN     = (12,  20,  44)
COLOR_ROW_HOVER    = (25,  40,  80)
COLOR_TEXT         = (255, 255, 255)
COLOR_TEXT_DIM     = (160, 170, 195)
COLOR_TIME_SOON    = (255, 220,  50)   # yellow  – < 5 min
COLOR_TIME_NOW     = (100, 230, 100)   # green   – < 2 min / "nå"
COLOR_CANCELLED    = (220,  60,  60)
COLOR_REALTIME_DOT = (100, 220, 100)
COLOR_DIVIDER      = (40,  55,  90)
COLOR_BADGE_DEFAULT = (180,  30,  50)  # Ruter red fallback

# ---- Fonts -------------------------------------------------------------
FONT_LARGE  = 64
FONT_MEDIUM = 42
FONT_SMALL  = 30
FONT_TINY   = 22

# ---- Entur API ---------------------------------------------------------
ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"
ENTUR_CLIENT_NAME = "personal-bus-display"   # identify your app to Entur
