"""Station extras: resuming an interrupted clean, mop drying time, ambient light.

From app_protol (Narwal app 2.9.90):

    GetContinueTask_Response { 1 taskRes, 2 errorCode, 3 cleanMode, 4 taskType,
                               5 taskStopTimestamp, 6 task, 7 mapId,
                               8 robotTerminatedPose, 9 finishedZoneIds[] }
                             (empty when there is nothing to continue)
    ContinueTask_Request     { 1 continueTask }   true resumes, false discards
    ContinueTask_Response    { 1 code, 2 result }
    GetDryMopRemainTime_Response { 1 result, 2 remainTime (seconds, verified) }
    AmbientLightCtrl_Request { 1 ambientLightCtrlType }

The ambient light's state is RobotBaseStatus field 50; the feature list's
maxAmbientLightCtrlType says which modes the station has.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import TaskResult, _NamedIntEnum
from .pb import WIRE_LEN, WIRE_VARINT, Writer, parse, parse_packed_varints

URL_GET_CONTINUE_TASK = "/task/get_continue_task"
URL_CONTINUE_TASK = "/task/continue_task"
URL_DRY_MOP_REMAIN = "/supply/get_dry_mop_remain_time"
URL_AMBIENT_LIGHT = "/supply/ambient_light_ctrl"


class AmbientLight(_NamedIntEnum):
    """AmbientLightCtrlType (the station's ambient light)."""

    OFF = 0
    NIGHT_LIGHT = 1
    WARM = 2  # "winter warmth"
    PURPLE = 3


class ContinueResult(_NamedIntEnum):
    """ContinueTask_Response.code."""

    UNSPECIFIED = 0
    CONTINUED = 1
    REPORT_UPLOADED = 2  # the interrupted task was closed instead
    FAILED = 3
    NOTHING_TO_CONTINUE = 4
    TASK_RUNNING = 5


@dataclass(frozen=True, slots=True)
class ContinueTask:
    """A clean that was interrupted and can be resumed."""

    result: TaskResult | int = TaskResult.UNSPECIFIED
    task_type: int = 0
    stopped_at: int = 0  # unix seconds
    map_id: int = 0
    finished_rooms: tuple[int, ...] = field(default_factory=tuple)


def decode_continue_task(payload: bytes) -> ContinueTask | None:
    """None when the robot has nothing to continue (empty answer)."""
    values: dict[int, int] = {}
    finished: tuple[int, ...] = ()
    for f in parse(payload):
        if f.wtype == WIRE_VARINT:
            values[f.num] = f.int
        elif f.num == 9 and f.wtype == WIRE_LEN:
            finished = tuple(parse_packed_varints(f.value))
    if not values and not finished:
        return None
    stopped = values.get(5, 0)
    return ContinueTask(
        result=TaskResult.from_value(values.get(1, 0)),
        task_type=values.get(4, 0),
        stopped_at=stopped // 1000 if stopped > 10**11 else stopped,  # ms or s
        map_id=values.get(7, 0),
        finished_rooms=finished,
    )


def build_continue_request(resume: bool) -> bytes:
    return bytes(Writer().varint(1, 1 if resume else 0, force=True))


def decode_continue_result(payload: bytes) -> ContinueResult | int:
    for f in parse(payload):
        if f.num == 1 and f.wtype == WIRE_VARINT:
            return ContinueResult.from_value(f.int)
    return ContinueResult.UNSPECIFIED


def decode_dry_mop_remain(payload: bytes) -> int:
    """Remaining mop drying time; 0 when the mop is not drying."""
    for f in parse(payload):
        if f.num == 2 and f.wtype == WIRE_VARINT:
            return f.int
    return 0


def build_ambient_light_request(mode: AmbientLight | int) -> bytes:
    return bytes(Writer().varint(1, int(mode), force=True))
