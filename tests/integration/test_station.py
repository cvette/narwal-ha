"""Station sensors and the readable error sensor."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.narwal_local.protocol import TaskType

from .conftest import FakeRobot, status_payload

DOCKED = {1: TaskType.IDLE, 3: 1}
# The real robot's station fields: clean water, dirty water, detergent,
# dust box, station bag (no robot dust bag, field 21).
STATION_OK = {23: 1, 24: 1, 12: 1, 20: 1, 39: 1}


async def test_station_sensors_for_reported_fields_only(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get("sensor.narwal_clean_water_tank").state == "normal"
    assert hass.states.get("sensor.narwal_dirty_water_tank").state == "normal"
    assert hass.states.get("sensor.narwal_detergent").state == "ok"
    assert hass.states.get("sensor.narwal_dust_box").state == "normal"
    assert hass.states.get("sensor.narwal_station_dust_bag").state == "ok"
    assert hass.states.get("sensor.narwal_dust_bag") is None, "field 21 not reported"
    for key in ("clean_water_empty", "dirty_water_full", "detergent_low"):
        assert hass.states.get(f"binary_sensor.narwal_{key}").state == STATE_OFF


async def test_station_problems(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    robot.push(
        "/status/robot_base_status",
        status_payload(DOCKED, charging=1, extra={**STATION_OK, 23: 2, 24: 2, 12: 4, 20: 4, 39: 3}),
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.narwal_clean_water_tank").state == "empty"
    assert hass.states.get("sensor.narwal_dirty_water_tank").state == "full_or_missing"
    assert hass.states.get("sensor.narwal_detergent").state == "running_out"
    assert hass.states.get("sensor.narwal_dust_box").state == "clean_suggested"
    assert hass.states.get("sensor.narwal_station_dust_bag").state == "replace_suggested"
    for key in ("clean_water_empty", "dirty_water_full", "detergent_low"):
        assert hass.states.get(f"binary_sensor.narwal_{key}").state == STATE_ON


async def test_error_sensor(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    assert hass.states.get("sensor.narwal_error").state == "none"

    robot.push("/status/robot_base_status", status_payload(DOCKED, errors=(0x02100063, 1201), extra=STATION_OK))
    await hass.async_block_till_done()
    state = hass.states.get("sensor.narwal_error")
    assert state.state == "stuck"
    assert state.attributes["codes"] == ["0x02100063", "0x000004B1"]
    assert state.attributes["categories"] == ["stuck", "unknown"]
    assert hass.states.get("vacuum.narwal").state == "error"

    robot.push("/status/robot_base_status", status_payload(DOCKED, errors=(1201,), extra=STATION_OK))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.narwal_error").state == "unknown"
