"""Build protocol/assets/errors.json: robot error code -> error category.

Input (not in the repo): an error table from the Narwal app, e.g.
app_res_config/lib/json/robot_exception/J4/en-US.json from the decompiled APK.
Only the factual mapping code -> category is kept; the texts shown in Home
Assistant are this project's own (scripts/object_names.py style, in
translations). Codes follow the firmware modules (0x01… station, 0x02… robot)
and are largely shared between models.

    python scripts/build_error_codes.py path/to/en-US.json
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "custom_components" / "narwal_local" / "protocol" / "assets" / "errors.json"

# (category, pattern on the English message); first match wins.
RULES: list[tuple[str, str]] = [
    ("station_power", r"base station is powered on|docking station is powered on|base station power|disconnect the base station"),
    ("low_battery", r"low battery"),
    ("battery_temperature", r"temperature|room temperature"),
    ("battery", r"battery"),
    ("return_to_dock", r"return to the base station|find the base station|return the robot"),
    ("charging", r"charging error|charging contacts"),
    ("dust_box", r"dust (box|bin|bag)"),
    ("map", r"obtain the map"),
    ("no_go_zone", r"no-go"),
    ("lifted", r"suspended"),
    ("stuck", r"stuck"),
    ("leave_dock", r"exit(ing)? the base station"),
    ("positioning", r"positioning failed"),
    ("wheel", r"tire|wheel"),
    ("side_brush", r"side brush"),
    ("roller_brush", r"roller brush"),
    ("mop", r"mop(ping)? (module|pad)|the mop can|mop module|mop washing|mop drying"),
    ("lidar", r"lidar|radar"),
    ("bumper", r"bumper"),
    ("sensor", r"sensor"),
    ("fan", r"fan abnormal"),
    ("top_cover", r"top cover"),
    ("clean_water_empty", r"fresh water tank is empty|water outlet error"),
    ("clean_water_tank_missing", r"clean water tank is not in place"),
    ("dirty_water_full", r"dirty water tank"),
    ("overflow", r"overflow"),
    ("water_pump", r"water pump"),
    ("water_module_missing", r"not (installed|detected)"),
    ("water_module", r"water exchange|water control"),
    ("cleaning_base", r"cleaning base"),
    ("station", r"base station malfunctions|dock"),
    ("system", r"system malfunction|robot malfunctions"),
    ("task_interrupted", r"interrupted|terminated|restart the task"),
]

CATEGORIES = [name for name, _ in RULES]


def categorize(message: str) -> str:
    for name, pattern in RULES:
        if re.search(pattern, message, re.IGNORECASE):
            return name
    raise ValueError(f"no category for: {message!r}")


def main() -> None:
    table = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    mapping = {}
    for key, entry in table.items():
        code = int(key, 16)
        mapping[f"0x{code:08X}"] = categorize(entry["message"])
    OUT.write_text(json.dumps(dict(sorted(mapping.items())), indent=1) + "\n", encoding="utf-8", newline="\n")
    counts = {c: list(mapping.values()).count(c) for c in CATEGORIES}
    print(f"{len(mapping)} codes -> {OUT}")
    print({c: n for c, n in counts.items() if n})


if __name__ == "__main__":
    main()
