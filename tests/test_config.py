"""Robot settings (/config/get, /config/set) and the clean report outcome."""

from __future__ import annotations

from datetime import time

import pytest

from protocol import DisturbMode, ReportTaskType, Setting, TaskResult, decode_clean_report, decode_config
from protocol.config import FIELDS, build_set_config_request
from protocol.pb import Writer, parse


def _config_response() -> bytes:
    """Shaped like the real robot's answer: region and a few nested and string
    fields around the settings this library reads."""
    region = Writer().string(1, "Europe/Somewhere").string(3, "Somewhere")
    dnd = Writer().varint(1, 1).varint(2, 79200).varint(3, 28800)
    config = (
        Writer()
        .varint(1, 20)
        .varint(2, 1)
        .message(3, region)
        .message(4, dnd)
        .varint(6, 1)
        .varint(8, 1)
        .message(14, Writer().varint(1, 3).varint(2, 7))
        .varint(27, 1)
        .varint(31, 1)
        .varint(32, 1)
        .string(45, "2026-01-01 00:00:00 UTC")
        .varint(51, 2)
    )
    return bytes(Writer().varint(1, 1).message(2, config))


def test_decode_config() -> None:
    config = decode_config(_config_response())
    assert config.volume == 20
    assert config.do_not_disturb == DisturbMode(True, time(22, 0), time(8, 0))
    assert config.flags == {
        Setting.AUTO_ADD_DETERGENT: True,
        Setting.CHILD_LOCK: False,  # left out = off
        Setting.DUST_GATHERING: True,
        Setting.QUIET_DUST_GATHERING: False,
        Setting.DRY_DUST_BAG: True,
        Setting.HOT_WATER_WASH: True,
    }
    assert config.raw_fields[51] == 2, "unnamed settings are kept"
    assert config.value(Setting.VOLUME) == 20


def test_decode_config_without_body() -> None:
    config = decode_config(bytes(Writer().varint(1, 2)))
    assert config.volume == 0 and config.flags == {}


def test_set_requests_use_the_set_field_numbers() -> None:
    # One field per request, at SetConfig's number, not Config's.
    [field] = parse(build_set_config_request(Setting.CHILD_LOCK, True))
    assert (field.num, field.int) == (8, 1)
    [field] = parse(build_set_config_request(Setting.DUST_GATHERING, False))
    assert (field.num, field.int) == (27, 0), "off is written, not left out"
    [field] = parse(build_set_config_request(Setting.VOLUME, 0))
    assert (field.num, field.int) == (1, 0)
    [field] = parse(build_set_config_request(Setting.DO_NOT_DISTURB, DisturbMode(True, time(21, 30), time(7))))
    assert field.num == 5
    assert {f.num: f.int for f in parse(field.value)} == {1: 1, 2: 77400, 3: 25200}


def test_set_request_validation() -> None:
    with pytest.raises(ValueError):
        build_set_config_request(Setting.VOLUME, 101)
    with pytest.raises(TypeError):
        build_set_config_request(Setting.DO_NOT_DISTURB, True)


def test_every_setting_has_field_numbers() -> None:
    assert set(FIELDS) == set(Setting)


def _report(task_type: int, result: int) -> bytes:
    w = Writer().varint(1, 100).float_(2, 16.0).varint(3, 1112).varint(4, 1).varint(5, task_type)
    return bytes(w.varint(6, 1792598354).varint(7, 1792600025).varint(8, result))


@pytest.mark.parametrize(
    ("result", "outcome"),
    [(1, "completed"), (11, "completed"), (2, "stopped"), (9, "stopped"), (10, "stopped"),
     (4, "interrupted"), (7, "interrupted"), (99, "interrupted")],
)  # fmt: skip
def test_clean_report_outcome(result: int, outcome: str) -> None:
    report = decode_clean_report(_report(3, result))
    assert report.task_type is ReportTaskType.SWEEP_MOP
    assert report.outcome == outcome


def test_clean_report_result() -> None:
    report = decode_clean_report(_report(6, 2))
    assert report.result is TaskResult.USER_FORCE_END
    assert report.task_type is ReportTaskType.CUSTOM
    assert (report.duration, report.start, report.end) == (1112, 1792598354, 1792600025)
