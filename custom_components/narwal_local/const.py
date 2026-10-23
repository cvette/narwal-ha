"""Constants for the Narwal Local integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "narwal_local"
MANUFACTURER: Final = "Narwal"

DEFAULT_PORT: Final = 9002

# The robot pushes status topics only for a limited time after
# /common/active_robot_publish; re-arm well before it lapses.
REPORT_SECONDS: Final = 60
KEEPALIVE_INTERVAL: Final = timedelta(seconds=45)

# The robot drops the connection now and then; reconnect after these delays
# (seconds) before reporting the entities unavailable.
RECONNECT_DELAYS: Final = (0.0, 2.0, 5.0)

# Live position: path points closer than this (cells, ~6 cm each) are merged;
# the path is capped for very long cleans. The map image is re-rendered at
# most this often while the robot moves.
PATH_MIN_STEP: Final = 0.5
PATH_MAX_POINTS: Final = 20_000
LIVE_MAP_INTERVAL: Final = timedelta(seconds=5)

# Fallback polling; pushes normally arrive much more often.
POLL_INTERVAL: Final = timedelta(seconds=60)
CONSUMABLES_INTERVAL: Final = timedelta(minutes=30)
MAP_INTERVAL: Final = timedelta(minutes=15)

# Timeline events kept for the last-event sensor's attribute.
TIMELINE_MAX: Final = 50
