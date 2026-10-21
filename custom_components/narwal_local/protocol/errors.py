"""Robot error codes (RobotBaseStatus field 1) -> error categories.

assets/errors.json maps each known code to one of ERROR_CATEGORIES; it is
built by scripts/build_error_codes.py from an error table in the Narwal app.
Codes follow the firmware modules (0x01… station, 0x02… robot) and are largely
shared between models; codes not in the table map to "unknown". Display texts
for the categories live in the integration's translations.
"""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

ERROR_CATEGORIES: tuple[str, ...] = (
    "battery",
    "battery_temperature",
    "bumper",
    "charging",
    "clean_water_empty",
    "clean_water_tank_missing",
    "cleaning_base",
    "dirty_water_full",
    "dust_box",
    "fan",
    "leave_dock",
    "lidar",
    "lifted",
    "low_battery",
    "map",
    "mop",
    "no_go_zone",
    "overflow",
    "positioning",
    "return_to_dock",
    "roller_brush",
    "sensor",
    "side_brush",
    "station",
    "station_power",
    "stuck",
    "system",
    "task_interrupted",
    "top_cover",
    "water_module",
    "water_module_missing",
    "water_pump",
    "wheel",
    "unknown",
)


@cache
def _table() -> dict[int, str]:
    raw = json.loads((ASSETS / "errors.json").read_text(encoding="utf-8"))
    return {int(code, 16): category for code, category in raw.items()}


def error_category(code: int) -> str:
    """The category of a robot error code, "unknown" if not in the table."""
    return _table().get(code, "unknown")


def error_hex(code: int) -> str:
    return f"0x{code:08X}"
