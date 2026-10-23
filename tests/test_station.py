"""Station extras: continue task, mop drying time, ambient light."""

from __future__ import annotations

from protocol.enums import TaskResult
from protocol.pb import Writer, parse
from protocol.station import (
    AmbientLight,
    ContinueResult,
    ContinueTask,
    build_ambient_light_request,
    build_continue_request,
    decode_continue_result,
    decode_continue_task,
    decode_dry_mop_remain,
)


def test_nothing_to_continue() -> None:
    assert decode_continue_task(b"") is None, "what the robot answers with nothing to resume"


def test_continue_task() -> None:
    payload = (
        Writer().varint(1, 4).varint(4, 5).varint(5, 1792600025123).varint(7, 1)
        .bytes_(9, bytes([1, 3]))
    )  # fmt: skip
    assert decode_continue_task(bytes(payload)) == ContinueTask(
        result=TaskResult.LOW_BATTERY_FORCE_END, task_type=5, stopped_at=1792600025, map_id=1, finished_rooms=(1, 3)
    )


def test_continue_requests() -> None:
    assert [(f.num, f.int) for f in parse(build_continue_request(True))] == [(1, 1)]
    assert [(f.num, f.int) for f in parse(build_continue_request(False))] == [(1, 0)], "false is written"
    assert decode_continue_result(bytes(Writer().varint(1, 1).varint(2, 1))) is ContinueResult.CONTINUED
    assert decode_continue_result(bytes(Writer().varint(1, 4))) is ContinueResult.NOTHING_TO_CONTINUE


def test_dry_mop_remain() -> None:
    assert decode_dry_mop_remain(b"") == 0
    assert decode_dry_mop_remain(bytes(Writer().varint(1, 1).varint(2, 5400))) == 5400


def test_ambient_light_request() -> None:
    assert [(f.num, f.int) for f in parse(build_ambient_light_request(AmbientLight.OFF))] == [(1, 0)]
    assert [(f.num, f.int) for f in parse(build_ambient_light_request(AmbientLight.PURPLE))] == [(1, 3)]
