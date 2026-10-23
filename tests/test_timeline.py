"""Cleaning timeline and voice language."""

from __future__ import annotations

from protocol.config import Language, build_set_language_request, decode_language, decode_supported_languages
from protocol.enums import TaskResult
from protocol.pb import Writer, parse
from protocol.timeline import CleanEvent, PrimaryTask, TimelineEvent, decode_clean_time_line, decode_timeline

T0 = 1792598355_000_000_000  # unix ns, as the robot sends them


def _node(t: int, task: int, event: int | None = None, zone: int | None = None, result: int | None = None, primary=False):
    node = Writer().varint(1, t).varint(2, task)
    if event is not None:
        sec = Writer().varint(1, event)
        if zone is not None:
            sec.message(2, Writer().varint(1, 1).varint(2, zone))
        node.message(3, sec)
    if result is not None:
        node.varint(5, result)
    return node.boolean(7, primary)


def test_timeline_like_the_recorded_clean() -> None:
    """Shaped like the pushes of the recorded clean (one event per push)."""
    status = (
        Writer()
        .message(1, _node(T0 + 2_000_000_000, 4, 1, zone=4, primary=True))
        .message(1, _node(T0, 1, primary=True))
        .message(1, _node(T0 + 3_000_000_000, 4, 15))
        .message(1, _node(T0 + 9_000_000_000, 6, result=1, primary=True))
    )
    events = decode_timeline(bytes(status))
    assert [e.time for e in events] == sorted(e.time for e in events), "oldest first"
    assert events[0] == TimelineEvent(T0 / 1e9, PrimaryTask.SELF_CHECK, None, None, None, True)
    assert events[1].event is CleanEvent.START and events[1].zone_id == 4
    assert events[2].event == 15, "codes the app does not know stay numbers"
    assert events[3].task is PrimaryTask.FINISHED and events[3].result is TaskResult.NORMAL_END


def test_clean_time_line_response() -> None:
    assert decode_clean_time_line(bytes(Writer().varint(1, 1).message(2, b""))) == [], "the robot's empty answer"
    one = Writer().varint(1, 1).message(2, Writer().message(1, _node(T0, 9, primary=True)))
    assert decode_clean_time_line(bytes(one))[0].task is PrimaryTask.DUST_GATHER


def test_language() -> None:
    assert decode_language(bytes(Writer().varint(1, 1).varint(2, 3))) is Language.ENGLISH
    supported = Writer().varint(1, 1).bytes_(2, bytes([10, 5, 1, 4, 11, 9, 3, 7]))
    assert decode_supported_languages(bytes(supported))[0] is Language.SPANISH, "as the robot lists them"
    assert [(f.num, f.int) for f in parse(build_set_language_request(Language.FRENCH))] == [(1, 9)]
