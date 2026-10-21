"""Live position, path on the map, current room and the clean report."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.narwal_local.protocol import TaskType

from .conftest import FakeRobot, clean_report_payload, display_map_payload, status_payload

IMAGE = "image.narwal_map"
ROOM = "sensor.narwal_current_room"
CLEANING = {1: TaskType.SWEEP_AND_MOP, 6: 7}


async def _start_clean(hass: HomeAssistant, robot: FakeRobot) -> None:
    robot.push("/status/robot_base_status", status_payload(CLEANING))
    await hass.async_block_till_done()


async def test_current_room_follows_live_position(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    await _start_clean(hass, robot)
    written: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: written.append(e.data["new_state"].state) if e.data["entity_id"] == ROOM else None,
    )
    robot.push("/map/display_map", display_map_payload(45, 20))  # living room
    robot.push("/map/display_map", display_map_payload(46, 21))  # still living room
    robot.push("/map/display_map", display_map_payload(70, 55))  # hallway
    robot.push("/map/display_map", display_map_payload(30, 80))  # bedroom
    await hass.async_block_till_done()
    assert hass.states.get(ROOM).state == "Bedroom"
    assert written == ["Hallway", "Bedroom"], "state written only when the room changes"


async def test_robot_and_path_on_map_with_throttle(
    hass: HomeAssistant, init_integration, robot: FakeRobot, hass_client, freezer: FrozenDateTimeFactory
) -> None:
    client = await hass_client()
    docked_png = await (await client.get(f"/api/image_proxy/{IMAGE}")).read()

    await _start_clean(hass, robot)
    stamp_clean = hass.states.get(IMAGE).state  # robot appeared: refreshed

    robot.push("/map/display_map", display_map_payload(35, 47))
    await hass.async_block_till_done()
    stamp_first = hass.states.get(IMAGE).state
    assert stamp_first != stamp_clean, "first movement refreshes at once"

    freezer.tick(timedelta(seconds=1))
    robot.push("/map/display_map", display_map_payload(40, 40))
    robot.push("/map/display_map", display_map_payload(45, 30))
    await hass.async_block_till_done()
    assert hass.states.get(IMAGE).state == stamp_first, "throttled within 5 s"

    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(IMAGE).state != stamp_first, "deferred refresh shows the last position"

    cleaning_png = await (await client.get(f"/api/image_proxy/{IMAGE}")).read()
    assert cleaning_png != docked_png

    robot.push("/status/robot_base_status", status_payload({1: TaskType.IDLE, 3: 1}, charging=1))
    await hass.async_block_till_done()
    resp = await client.get(f"/api/image_proxy/{IMAGE}")
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == docked_png, "no robot or path once docked"


async def test_new_clean_starts_new_path(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    coordinator = init_integration.runtime_data
    await _start_clean(hass, robot)
    for col in (35, 40, 45):
        robot.push("/map/display_map", display_map_payload(col, 40))
    await hass.async_block_till_done()
    assert len(coordinator.live.path) == 3

    robot.push("/status/robot_base_status", status_payload({1: TaskType.IDLE, 3: 1}))
    await hass.async_block_till_done()
    assert len(coordinator.live.path) == 3, "kept after the clean"

    await _start_clean(hass, robot)
    assert coordinator.live.path == []


async def test_clean_report_sensors(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    assert hass.states.get("sensor.narwal_last_clean").state == "unknown"
    end = 1792600025
    robot.push("/report/clean_report", clean_report_payload(16.0092, 1112, end - 1671, end))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.narwal_last_clean").state == datetime.fromtimestamp(end, UTC).isoformat()
    assert hass.states.get("sensor.narwal_last_clean_area").state == "16.01"
    duration = hass.states.get("sensor.narwal_last_clean_duration")
    assert abs(float(duration.state) - 1112 / 60) < 0.01  # shown in minutes


async def test_last_clean_survives_restart(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.narwal_last_clean_area", "16.01"),
                {"native_value": 16.01, "native_unit_of_measurement": "m²"},
            )
        ],
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.narwal_last_clean_area").state == "16.01"
