"""The cleaning timeline: what the robot did during the last task.

/info/get_clean_time_line answers {1 result, 2 TimeLineStatus}; the robot also
pushes TimeLineStatus on /status/time_line_status while it works.

    TimeLineStatus      { 1 robotEventList[]: RobotEventNode }
    RobotEventNode      { 1 eventTime (unix ns), 2 primaryTask,
                          3 secondaryCleanEvent, 4 secondarySelfCheck,
                          5 taskResult, 6 errorCode, 7 isPrimaryNode, 8 nodeKey }
    SecondaryCleanEvent { 1 secondaryEvent, 2 zoneInfo: EventZoneInfo,
                          3 fanLevel, 4 mopHumidity, … }
    EventZoneInfo       { 1 zoneType, 2 zoneId, 3 cleanCount, 4 cleanMode, … }

From app_protol (Narwal app 2.9.90).
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import TaskResult, _NamedIntEnum
from .pb import WIRE_LEN, WIRE_VARINT, parse

URL_CLEAN_TIME_LINE = "/info/get_clean_time_line"
TOPIC_TIME_LINE = "/status/time_line_status"


class PrimaryTask(_NamedIntEnum):
    UNSPECIFIED = 0
    SELF_CHECK = 1
    DEPARTURE = 2
    WASH_MOP_BEFORE_CLEAN = 3
    CLEAN = 4
    UNEXPECTED_PAUSE = 5
    FINISHED = 6
    ZONE_NOT_CLEAN = 7
    MAINTAIN_FLOOR = 8
    DUST_GATHER = 9
    UPDATE_MAP_REGION = 10


class CleanEvent(_NamedIntEnum):
    """ZoneCleanEventType: what happened within a task."""

    UNSPECIFIED = 0
    START = 1
    FINISH = 2
    NAVI_TO_STATION = 3
    WASH_MOP = 4
    SECOND_CLEAN = 5
    MANUAL_WASH_MOP_START = 6
    MANUAL_WASH_MOP_CANCEL = 7
    MANUAL_ADJUST_SUCTION = 8
    PAUSE = 9
    DEPARTURE = 16
    LONG_TIME_NO_CLEAN = 17
    HEAVY_POLLUTION = 18
    HUMIDITY_EXCEEDS_THRESHOLD = 19
    ADJUST_PRESSURE = 20
    CARPET_CLEAN = 21
    TRAP = 22
    UNEXPECTED_PAUSE = 23
    AUTO_WASH_MOP_START = 24
    PARKING = 25
    ROOM_CHANGE = 26
    AUTO_RESUME = 27
    EXCEPTION_SOLVED = 28
    COMPRESS_DUST_BAG = 29
    MANUAL_ADJUST_MOP_HUMIDITY = 30
    START_CLEAN_MANY_SOLID_DIRTY = 31
    START_CLEAN_MANY_LIQUID_DIRTY = 32
    START_CLEAN_MASSIVE_SOLID_DIRTY = 33
    START_CLEAN_MASSIVE_LIQUID_DIRTY = 34
    MAINTAIN_FLOOR_START = 35
    MAINTAIN_FLOOR_FINISH = 36
    CLEAN_VISUAL_DIRTY_FINISH = 37
    HEAVY_DIRTY_CLEAN_MANUAL = 38
    HEAVY_DIRTY_CLEAN_SMART = 39
    CHANGE_CLEAN_SEQUENCE = 40
    RESUME_TASK_AFTER_RECHARGE = 41
    NOT_CLEAN = 100
    BLOCKED_ROOM_REPLENISH_CLEAN = 101
    REDUCE_NOISE = 110
    FOUND_CARD = 154
    FOUND_HEADPHONES = 155
    FOUND_GLASSES = 156
    FOUND_WATCH = 157
    FOUND_JEWELRY = 158
    FOUND_BANKNOTE = 159


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    time: float  # unix seconds
    task: PrimaryTask | int = PrimaryTask.UNSPECIFIED
    event: CleanEvent | int | None = None  # set on sub-events
    zone_id: int | None = None  # the room, for room events
    result: TaskResult | int | None = None  # set when the task ended
    primary: bool = False


def _secondary(buf: bytes) -> tuple[CleanEvent | int | None, int | None]:
    event = zone = None
    for f in parse(buf):
        if f.num == 1 and f.wtype == WIRE_VARINT:
            event = CleanEvent.from_value(f.int)
        elif f.num == 2 and f.wtype == WIRE_LEN:
            for g in parse(f.value):
                if g.num == 2 and g.wtype == WIRE_VARINT:
                    zone = g.int
    return event, zone


def decode_timeline(payload: bytes) -> list[TimelineEvent]:
    """Events of a TimeLineStatus, oldest first."""
    events = []
    for f in parse(payload):
        if f.num != 1 or f.wtype != WIRE_LEN:
            continue
        values: dict[int, int] = {}
        event = zone = None
        for g in parse(f.value):
            if g.wtype == WIRE_VARINT:
                values[g.num] = g.int
            elif g.num == 3 and g.wtype == WIRE_LEN:
                event, zone = _secondary(g.value)
        events.append(
            TimelineEvent(
                time=values.get(1, 0) / 1e9,
                task=PrimaryTask.from_value(values.get(2, 0)),
                event=event,
                zone_id=zone,
                result=TaskResult.from_value(values[5]) if 5 in values else None,
                primary=bool(values.get(7)),
            )
        )
    return sorted(events, key=lambda e: e.time)


def decode_clean_time_line(payload: bytes) -> list[TimelineEvent]:
    """GetCleanTimeLine_Response {1 result, 2 TimeLineStatus}."""
    for f in parse(payload):
        if f.num == 2 and f.wtype == WIRE_LEN:
            return decode_timeline(f.value)
    return []
