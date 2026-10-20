"""Status and device decoders against real robot payloads and the Go golden output."""

from __future__ import annotations

import pytest

from protocol.enums import (
    ChargingStatus,
    FanLevel,
    FirmwareStatus,
    IdleStatus,
    MopHumidity,
    ServiceResult,
    TaskType,
)
from protocol.models import (
    Activity,
    decode_check_firmware,
    decode_consumable_info,
    decode_device_base_status,
    decode_device_info,
    decode_feature_list,
    decode_firmware_version,
    decode_robot_base_status,
    decode_working_status,
)
from protocol.pb import Writer


def _assert_status_matches_go(st, gold) -> None:
    assert st.battery == gold["battery"]
    assert int(st.fan_level) == gold["fanLevel"]
    assert int(st.mop_humidity) == gold["mopHumidity"]
    assert st.map_id == gold["mapId"]
    assert st.has_station == gold["hasStation"]
    assert st.is_robot_at_origin == gold["atOrigin"]
    assert st.charging_status == gold["chargingStatus"]
    assert st.battery_cooling == gold["batteryCooling"]
    assert st.binded_uuid == gold["bindedUuid"]
    assert {str(k): v for k, v in st.raw_fields.items()} == gold["fields"]


def test_device_base_status(fixture_bin, golden) -> None:
    st = decode_device_base_status(fixture_bin("device_base_status"))
    gold = golden("device_base_status")
    assert st.result is ServiceResult.PERFORM_SUCCESS
    _assert_status_matches_go(st, gold)
    assert st.fan_level is FanLevel.NORMAL
    assert st.mop_humidity is MopHumidity.WET
    # Field 3 (robotTaskStatus) is skipped by the Go decoder; we keep it raw.
    assert st.robot_task_status, "robotTaskStatus should be decoded"


def test_robot_base_status_push(fixture_bin, golden) -> None:
    gold = golden("push_status_robot_base_status")
    assert gold["url"] == "/status/robot_base_status"
    st = decode_robot_base_status(fixture_bin("push_status_robot_base_status"))
    _assert_status_matches_go(st, gold["decoded"])


def test_device_info_is_redacted_and_trimmed(fixture_bin, golden) -> None:
    di = decode_device_info(fixture_bin("device_info"))
    gold = golden("device_info")
    assert di.token == gold["Token"] == "x" * len(gold["Token"])
    assert di.device_id == gold["DeviceID"]
    assert di.firmware_version == gold["FirmwareVersion"].strip() == "v01.09.05.04"


def test_feature_list(fixture_bin, golden) -> None:
    fl = decode_feature_list(fixture_bin("feature_list"))
    gold = golden("feature_list")
    assert fl.enabled == gold["enabled"]
    assert fl.other == gold["other"]
    assert fl.supports("supportMultiZoneClean")
    assert not fl.supports("supportVirtualWall")


def test_consumables(fixture_bin, golden) -> None:
    ci = decode_consumable_info(fixture_bin("consumable_info"))
    gold = golden("consumable_info")
    assert ci.maintain_items == gold["MaintainItems"]
    assert ci.replace_items == gold["ReplaceItems"]
    assert ci.unified_error_code == gold["UnifiedErrorCode"]


def test_firmware_version(fixture_bin) -> None:
    fv = decode_firmware_version(fixture_bin("firmware_version"))
    assert fv.version_text == "v01.09.05.04"
    got = {(m.group, m.slot, m.firmware_id, m.version_text) for m in fv.modules}
    assert got == {
        ("robot", "mcu", "0210_DR_GD03", "v01.09.05.04"),
        ("robot", "ble", "0211_WL_COMB", "v03.05.15.01"),
        ("robot", "cpu", "0200_OA_813A", "v01.09.05.04"),
        ("robot", "sensor", "0220_SS_SY02C", "v00.00.01.07"),
        ("station", "ble", "0102_WL_TEK1", "v01.09.05.04"),
        ("station", "cpu", "0100_BM_HC01", "v01.09.05.04"),
    }


def test_check_firmware(fixture_bin) -> None:
    assert decode_check_firmware(fixture_bin("check_firmware")) is FirmwareStatus.NO_PACKAGE


def test_working_status_synthetic() -> None:
    # No live capture yet (the robot only pushes this while cleaning).
    body = bytes(
        Writer().float_(1, 42.5).float_(2, 12.25).varint(3, 600).varint(4, 900).varint(6, 3)
    )
    ws = decode_working_status(body)
    assert (ws.working_progress, ws.covered_area) == (42.5, 12.25)
    assert (ws.time_consuming, ws.remained_time, ws.cleaning_zone_id) == (600, 900, 3)


def test_live_docked_status_is_docked(fixture_bin) -> None:
    st = decode_device_base_status(fixture_bin("device_base_status"))
    assert st.task is TaskType.IDLE
    assert st.idle_status is IdleStatus.LOW_POWER_IN_STATION
    assert st.charging_status is ChargingStatus.NOT_CHARGING
    assert st.activity is Activity.DOCKED


def _status(task: dict[int, int], *, errors: tuple[int, ...] = (), charging: int = 0):
    inner = Writer()
    for e in errors:
        inner.varint(1, e, force=True)
    tw = Writer()
    for num, value in task.items():
        tw.varint(num, value, force=True)
    inner.message(3, tw).varint(47, charging)
    return decode_device_base_status(bytes(Writer().varint(1, 1).message(2, inner)))


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ({1: TaskType.SWEEP, 4: 3}, Activity.CLEANING),  # sweep, ROOM_CLEAN
        ({1: TaskType.SWEEP, 4: 1}, Activity.RETURNING),  # sweep, RECALL
        ({1: TaskType.SWEEP_AND_MOP, 6: 2}, Activity.RETURNING),  # AUTO_RECALL_TO_WASH
        ({1: TaskType.SWEEP_AND_MOP, 6: 4}, Activity.DOCKED),  # AUTO_WASH mid-clean
        ({1: TaskType.MOP, 2: 1}, Activity.PAUSED),
        ({1: TaskType.RECALL}, Activity.RETURNING),
        ({1: TaskType.DUST_GATHERING}, Activity.DOCKED),
        ({1: TaskType.IDLE, 3: IdleStatus.OUTSIDE_STATION}, Activity.IDLE),
        ({1: TaskType.IDLE, 3: IdleStatus.IN_STATION}, Activity.DOCKED),
    ],
)
def test_activity_mapping(task, expected) -> None:
    assert _status(task).activity is expected


def test_error_wins_over_task() -> None:
    assert _status({1: TaskType.SWEEP, 4: 3}, errors=(1201,)).activity is Activity.ERROR


def test_charging_fallback_is_docked() -> None:
    assert _status({}, charging=ChargingStatus.CHARGING).activity is Activity.DOCKED


def test_unknown_enum_values_stay_numeric() -> None:
    body = bytes(Writer().message(2, Writer().varint(26, 99)))
    assert decode_device_base_status(body).fan_level == 99
