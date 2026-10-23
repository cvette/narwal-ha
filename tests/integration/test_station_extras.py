"""Resume button, extra station buttons, mop drying time, ambient light."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.narwal_local.const import POLL_INTERVAL
from custom_components.narwal_local.protocol import AmbientLight, ContinueTask

from .conftest import FakeRobot

CONTINUE = "button.narwal_resume_interrupted_clean"
LIGHT = "select.narwal_ambient_light"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(POLL_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _press(hass: HomeAssistant, entity: str) -> None:
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: entity}, blocking=True)


async def test_resume_interrupted_clean(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    assert hass.states.get(CONTINUE).state == STATE_UNAVAILABLE, "nothing to resume"
    robot.continue_task_info = ContinueTask(task_type=5, map_id=1)
    await _poll(hass, freezer)
    assert hass.states.get(CONTINUE).state != STATE_UNAVAILABLE
    await _press(hass, CONTINUE)
    assert robot.calls[-1] == ("continue_task", True)


@pytest.mark.parametrize(
    ("entity", "call"),
    [("button.narwal_wash_and_dry_mop", "wash_and_dry_mop"), ("button.narwal_dry_station_dust_bag", "dry_station_bag")],
)
async def test_more_station_buttons(
    hass: HomeAssistant, init_integration, robot: FakeRobot, entity: str, call: str
) -> None:
    await _press(hass, entity)
    assert robot.calls[-1] == (call,)


async def test_dust_bag_button_only_with_a_robot_bag(hass: HomeAssistant, init_integration) -> None:
    # The fixture robot reports a station bag (field 39) but no bag of its own (field 21).
    assert hass.states.get("button.narwal_dry_dust_bag") is None


async def test_mop_drying_time(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    sensor = "sensor.narwal_mop_drying_time_left"
    assert float(hass.states.get(sensor).state) == 0
    robot.dry_remain = 5400
    await _poll(hass, freezer)
    state = hass.states.get(sensor)
    assert float(state.state) == 90 and state.attributes["unit_of_measurement"] == "min"


async def test_ambient_light(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    state = hass.states.get(LIGHT)
    assert state.state == "off"
    assert state.attributes["options"] == ["off", "night_light", "warm", "purple"]
    await hass.services.async_call("select", "select_option", {ATTR_ENTITY_ID: LIGHT, "option": "warm"}, blocking=True)
    assert robot.calls[-1] == ("set_ambient_light", AmbientLight.WARM)
