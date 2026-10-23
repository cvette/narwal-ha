"""Requests that start, end and locate a clean.

Reconstructed from the app (2.9.90) and verified on a robot: the app's start
function sends /clean/start_clean with a CleanTask for every model except the
"ax3", which gets /clean/easy_clean/start (kept below, unverified); ending a
clean sends an empty /task/force_end ("end all running tasks"); "find my
robot" sends an empty /common/yell.

The easy-clean ("ax3") request:

    StartEasyClean_Request { 1 cleanMode, 2 mapId, 3 cleanAreaOptions[] }
    CleanAreaOption        { 1 zoneId, 2 cleanZoneType,
                             4 sweep / 5 mop / 6 sweep+mop / 7 sweep-then-mop option }
    SweepAreaOption        { 1 sweepFanLevel, 2 cleanCount }
    MopAreaOption          { 1 mopStrengthLevel, 2 mopHumidityLevel, 3 cleanCount }
    SweepMopSyncAreaOption { 1 sweepFanLevel, 2 mopStrengthLevel, 3 mopHumidityLevel, 4 cleanCount }
    SweepThenMopAreaOption { 1 SweepAreaOption, 2 MopAreaOption }
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from .enums import FanLevel, MopHumidity
from .pb import WIRE_LEN, WIRE_VARINT, Writer, parse

URL_START = "/clean/easy_clean/start"
URL_END = "/task/force_end"
URL_LOCATE = "/common/yell"


class CleanMode(IntEnum):
    """CleanMode of a clean plan."""

    SMART = 1
    SWEEP = 2
    MOP = 3
    SWEEP_MOP = 4  # vacuum and mop in one pass
    SWEEP_THEN_MOP = 5


class CleanZoneType(IntEnum):
    ROOM = 1
    ZONE = 2
    WHOLE_HOUSE = 3


def _sweep_fan(level: FanLevel | int) -> int:
    """SweepFanLevel stops at DEEP (4); FanLevel goes up to SUPER (5)."""
    return max(1, min(int(level), 4))


def _sweep_option(fan: FanLevel | int, count: int) -> Writer:
    return Writer().varint(1, _sweep_fan(fan)).varint(2, count)


def _mop_option(humidity: MopHumidity | int, count: int) -> Writer:
    return Writer().varint(2, int(humidity)).varint(3, count)


def _area_option(
    zone_type: CleanZoneType,
    room_id: int | None,
    mode: CleanMode,
    fan: FanLevel | int,
    humidity: MopHumidity | int,
    count: int,
) -> Writer:
    opt = Writer()
    if room_id is not None:
        opt.varint(1, room_id)
    opt.varint(2, int(zone_type))
    if mode is CleanMode.SWEEP:
        opt.message(4, _sweep_option(fan, count))
    elif mode is CleanMode.MOP:
        opt.message(5, _mop_option(humidity, count))
    elif mode is CleanMode.SWEEP_MOP:
        opt.message(
            6,
            Writer().varint(1, _sweep_fan(fan)).varint(3, int(humidity)).varint(4, count),
        )
    elif mode is CleanMode.SWEEP_THEN_MOP:
        opt.message(7, Writer().message(1, _sweep_option(fan, count)).message(2, _mop_option(humidity, count)))
    # SMART: the robot picks its own settings, no per-area option.
    return opt


def build_start_request(
    map_id: int,
    rooms: Sequence[int] | None = None,
    *,
    mode: CleanMode = CleanMode.SWEEP_MOP,
    fan: FanLevel | int = FanLevel.NORMAL,
    humidity: MopHumidity | int = MopHumidity.NORMAL,
    count: int = 1,
) -> bytes:
    """StartEasyClean_Request: the given rooms in this order, or the whole home."""
    req = Writer().varint(1, int(mode), force=True).varint(2, map_id)
    if rooms:
        for room_id in rooms:
            req.message(3, _area_option(CleanZoneType.ROOM, room_id, mode, fan, humidity, count))
    else:
        req.message(3, _area_option(CleanZoneType.WHOLE_HOUSE, None, mode, fan, humidity, count))
    return bytes(req)


# --- /clean/start_clean (every model except the "ax3") ----------------------
#
# The app's start function sends /clean/easy_clean/start only for the "ax3"
# model; every other model gets StartClean_Request { 1 task: CleanTask }:
#
#   CleanTask  { 1 mapId, 2 items[], 3 option, 5 taskType, … }
#   CleanItem  { 1 zone: ZoneOption, 2 param: CleanParam, 3 order }
#   ZoneOption { 1 zoneType (1 room, 2 zone, 3 whole map), 2 zoneId }
#   CleanParam { 1 mode (CleanMode), 2 fanLevel, 3 mopStrengthLevel,
#                4 mopHumidity, 5 sweepTime, 6 mopTime, 7 sweepMopSyncTime, … }

URL_START_LEGACY = "/clean/start_clean"


class TaskKind(IntEnum):
    """CleanTask.taskType."""

    GENERAL_SWEEP = 1
    GENERAL_MOP = 2
    GENERAL_SWEEP_THEN_MOP = 3
    GENERAL_SWEEP_MOP = 4
    CUSTOM = 5  # rooms with their own parameters


class ZoneKind(IntEnum):
    """ZoneOption.zoneType."""

    ROOM = 1
    ZONE = 2
    WHOLE_MAP = 3


def _clean_param(mode: CleanMode, fan: FanLevel | int, humidity: MopHumidity | int, count: int) -> Writer:
    param = Writer().varint(1, int(mode)).varint(2, int(fan)).varint(4, int(humidity))
    if mode is CleanMode.SWEEP:
        param.varint(5, count)
    elif mode is CleanMode.MOP:
        param.varint(6, count)
    elif mode is CleanMode.SWEEP_MOP:
        param.varint(7, count)
    elif mode is CleanMode.SWEEP_THEN_MOP:
        param.varint(5, count).varint(6, count)
    return param


def build_clean_task_request(
    map_id: int,
    rooms: Sequence[int] | None = None,
    *,
    mode: CleanMode = CleanMode.SWEEP_MOP,
    fan: FanLevel | int = FanLevel.NORMAL,
    humidity: MopHumidity | int = MopHumidity.NORMAL,
    count: int = 1,
    task_kind: TaskKind = TaskKind.CUSTOM,
    include_whole_map_item: bool = False,
) -> bytes:
    """StartClean_Request for the given rooms (in this order) or the whole map."""
    task = Writer().varint(1, map_id)
    if rooms:
        targets = [(ZoneKind.ROOM, r) for r in rooms]
    elif task_kind is TaskKind.CUSTOM:
        targets = [(ZoneKind.WHOLE_MAP, None)]
    else:
        targets = [(ZoneKind.WHOLE_MAP, None)] if include_whole_map_item else []
    for order, (kind, room_id) in enumerate(targets, start=1):
        zone = Writer().varint(1, int(kind))
        if room_id is not None:
            zone.varint(2, room_id)
        item = Writer().message(1, zone).message(2, _clean_param(mode, fan, humidity, count)).varint(3, order)
        task.message(2, item)
    task.varint(5, int(task_kind))
    return bytes(Writer().message(1, task))


# --- zones -------------------------------------------------------------------
#
# The app's map editor sends a drawn rectangle as a CleanItem whose zone is
#
#   ZoneOption { 1 zoneType ZONE, 2 zoneId (the area's number),
#                3 selectionBounds[], 4 cleaningBounds[] }
#   GridPoint  { 1 x, 2 y }
#
# with both bounds holding the rectangle's four corners as integer cells in
# the map's border frame (the frame of doors and carpets). The task type is
# the "general" one for the clean mode, as the app sends it; the robot accepts
# zones in a CUSTOM task but does not start them.

GridRect = tuple[int, int, int, int]  # x1, y1, x2, y2 in border-frame cells

GENERAL_TASKS: dict[CleanMode, TaskKind] = {
    CleanMode.SWEEP: TaskKind.GENERAL_SWEEP,
    CleanMode.MOP: TaskKind.GENERAL_MOP,
    CleanMode.SWEEP_MOP: TaskKind.GENERAL_SWEEP_MOP,
    CleanMode.SWEEP_THEN_MOP: TaskKind.GENERAL_SWEEP_THEN_MOP,
}


def _corners(rect: GridRect) -> list[tuple[int, int]]:
    x1, y1, x2, y2 = rect
    left, right = sorted((x1, x2))
    bottom, top = sorted((y1, y2))
    if left == right or bottom == top:
        raise ValueError(f"zone {rect} has no area")
    return [(left, bottom), (right, bottom), (right, top), (left, top)]


def _zone_option(zone_id: int, rect: GridRect) -> Writer:
    zone = Writer().varint(1, int(ZoneKind.ZONE)).varint(2, zone_id)
    corners = _corners(rect)
    for field_num in (3, 4):
        for x, y in corners:
            zone.message(field_num, Writer().varint(1, x, force=True).varint(2, y, force=True))
    return zone


def build_zone_clean_request(
    map_id: int,
    zones: Sequence[GridRect],
    *,
    mode: CleanMode = CleanMode.SWEEP_MOP,
    fan: FanLevel | int = FanLevel.NORMAL,
    humidity: MopHumidity | int = MopHumidity.NORMAL,
    count: int = 1,
) -> bytes:
    """StartClean_Request for rectangular zones, cleaned in the given order."""
    if not zones:
        raise ValueError("no zones given")
    if mode not in GENERAL_TASKS:
        raise ValueError(f"zones cannot be cleaned in mode {mode!r}")
    task = Writer().varint(1, map_id)
    for order, rect in enumerate(zones, start=1):
        item = Writer().message(1, _zone_option(order, rect))
        item.message(2, _clean_param(mode, fan, humidity, count)).varint(3, order)
        task.message(2, item)
    task.varint(5, int(GENERAL_TASKS[mode]))
    return bytes(Writer().message(1, task))


# --- cleaning plans ------------------------------------------------------------
#
# Plans are the room selections saved in the app. /clean/plan/get answers
# GetCleanPlans_Response { 1 result, 2 cleanPlans[] } with
#
#   CleanPlan { 1 id, 2 mapId, 3 cleanMode, 4 isCustomPlan, 5 customName,
#               6 shownInStation, 7 performTimes, 8 order, … }
#
# and /clean/plan/start takes StartWithPlan_Request { 1 planId, 2 mapId }.

URL_GET_PLANS = "/clean/plan/get"
URL_START_PLAN = "/clean/plan/start"


@dataclass(frozen=True, slots=True)
class CleanPlan:
    id: int
    map_id: int = 0
    mode: CleanMode | int = 0
    custom: bool = False
    name: str = ""
    order: int = 0


def decode_clean_plans(payload: bytes) -> list[CleanPlan]:
    plans = []
    for f in parse(payload):
        if f.num != 2 or f.wtype != WIRE_LEN:
            continue
        values: dict[int, int | str] = {}
        for g in parse(f.value):
            if g.wtype == WIRE_VARINT:
                values[g.num] = g.int
            elif g.num == 5 and g.wtype == WIRE_LEN:
                values[5] = g.value.decode("utf-8", "replace")
        mode = values.get(3, 0)
        plans.append(
            CleanPlan(
                id=int(values.get(1, 0)),
                map_id=int(values.get(2, 0)),
                mode=CleanMode(mode) if mode in CleanMode._value2member_map_ else mode,
                custom=bool(values.get(4)),
                name=str(values.get(5, "")),
                order=int(values.get(8, 0)),
            )
        )
    return sorted(plans, key=lambda p: (p.order, p.id))


def build_start_plan_request(plan_id: int, map_id: int) -> bytes:
    return bytes(Writer().varint(1, plan_id, force=True).varint(2, map_id))


# --- go to a point: not usable ----------------------------------------------
#
# The app's "drive here" exists only in its live video view and sends
# /telecontrol/point_navi { 4 points[]: PoseData{1 point (border-frame cells)} }.
# Sent outside a video session (twice, byte for byte as the app sends it,
# robot docked and idle) the robot dropped the connection and restarted its
# control software; it recovered on its own. So it is not offered here.
