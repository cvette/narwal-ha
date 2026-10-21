"""Vacuum, sensors, binary sensors and select."""

from __future__ import annotations

import pytest

from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.vacuum import (
    ATTR_FAN_SPEED,
    ATTR_FAN_SPEED_LIST,
    SERVICE_PAUSE,
    SERVICE_RETURN_TO_BASE,
    SERVICE_SET_FAN_SPEED,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.narwal_local.protocol import FanLevel, MopHumidity, ServiceResult, TaskType

from .conftest import FakeRobot, status_payload, working_payload

VACUUM = "vacuum.narwal"


async def _call(hass: HomeAssistant, domain: str, service: str, entity: str, **data) -> None:
    await hass.services.async_call(domain, service, {ATTR_ENTITY_ID: entity, **data}, blocking=True)


async def test_vacuum_docked_state(hass: HomeAssistant, init_integration) -> None:
    state = hass.states.get(VACUUM)
    assert state.state == "docked"
    assert state.attributes[ATTR_FAN_SPEED] == "normal"
    assert state.attributes[ATTR_FAN_SPEED_LIST] == ["mute", "normal", "strong", "deep", "super"]


async def test_vacuum_commands(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "vacuum", SERVICE_RETURN_TO_BASE, VACUUM)
    await _call(hass, "vacuum", SERVICE_PAUSE, VACUUM)
    await _call(hass, "vacuum", SERVICE_SET_FAN_SPEED, VACUUM, fan_speed="strong")
    assert ("dock",) in robot.calls
    assert ("pause",) in robot.calls
    assert ("set_fan_level", FanLevel.STRONG) in robot.calls


async def test_rejected_command_raises(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    robot.fail_command = ServiceResult.ROBOT_IN_STATION_WHEN_RECALL
    with pytest.raises(HomeAssistantError, match="ROBOT_IN_STATION_WHEN_RECALL"):
        await _call(hass, "vacuum", SERVICE_RETURN_TO_BASE, VACUUM)


async def test_static_sensors(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get("sensor.narwal_battery").state == "100"
    assert hass.states.get("sensor.narwal_task").state == "idle"
    assert hass.states.get("sensor.narwal_charging_status").state == "not_charging"
    assert hass.states.get("sensor.narwal_error_code").state == "0"
    maintenance = hass.states.get("sensor.narwal_maintenance_due")
    assert maintenance.state == "1"
    assert maintenance.attributes["items"] == ["side_distance_sensor"]
    assert hass.states.get("sensor.narwal_replacement_due").attributes["items"] == ["station_bag"]
    assert hass.states.get("binary_sensor.narwal_maintenance_needed").state == STATE_ON
    assert hass.states.get("binary_sensor.narwal_charging").state == STATE_OFF
    # Nothing has been cleaned since setup.
    assert hass.states.get("sensor.narwal_cleaned_area").state == "unknown"
    # Docked: the room of the robot's saved position, which is the dock.
    assert hass.states.get("sensor.narwal_current_room").state == "Living room"
    assert hass.states.get("sensor.narwal_remaining_time") is None, "retired in 0.4.0"


async def test_pushes_update_cleaning_sensors(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    robot.push("/status/robot_base_status", status_payload({1: TaskType.SWEEP_AND_MOP, 6: 7}))
    robot.push("/status/working_status", working_payload(37.0, 12.5, 600, 900, 3))
    await hass.async_block_till_done()

    assert hass.states.get(VACUUM).state == "cleaning"
    assert hass.states.get(VACUUM).attributes[ATTR_FAN_SPEED] == "strong"
    assert hass.states.get("sensor.narwal_battery").state == "80"
    assert hass.states.get("sensor.narwal_task").state == "sweep_and_mop"
    assert hass.states.get("sensor.narwal_charging_status").state == "discharging"
    assert hass.states.get("sensor.narwal_cleaning_progress").state == "37.0"
    assert hass.states.get("sensor.narwal_cleaned_area").state == "12.5"
    assert hass.states.get("sensor.narwal_cleaning_time").state == "10.0"
    # The robot's zone id (3 = Hallway) is ignored: it runs ahead of the robot.
    # Without a live position the room stays the one of the last known pose.
    assert hass.states.get("sensor.narwal_current_room").state == "Living room"

    robot.push("/status/robot_base_status", status_payload({1: TaskType.SWEEP_AND_MOP, 6: 1}))
    await hass.async_block_till_done()
    assert hass.states.get(VACUUM).state == "returning"

    robot.push("/status/robot_base_status", status_payload({1: TaskType.SWEEP, 4: 3}, errors=(1201,)))
    await hass.async_block_till_done()
    assert hass.states.get(VACUUM).state == "error"
    assert hass.states.get("sensor.narwal_error_code").state == "1201"


async def test_mop_humidity_select(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    state = hass.states.get("select.narwal_mop_humidity")
    assert state.state == "wet"
    assert state.attributes["options"] == ["dry", "normal", "wet"]
    await _call(hass, "select", SERVICE_SELECT_OPTION, "select.narwal_mop_humidity", **{ATTR_OPTION: "dry"})
    assert ("set_mop_humidity", MopHumidity.DRY) in robot.calls
