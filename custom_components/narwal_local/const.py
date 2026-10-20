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

# Fallback polling; pushes normally arrive much more often.
POLL_INTERVAL: Final = timedelta(seconds=60)
CONSUMABLES_INTERVAL: Final = timedelta(minutes=30)
MAP_INTERVAL: Final = timedelta(minutes=15)
