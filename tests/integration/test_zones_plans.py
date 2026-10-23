"""Zone cleaning (clean_zone action, map calibration) and the app's cleaning plans."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.narwal_local.const import DOMAIN, MAP_INTERVAL
from custom_components.narwal_local.protocol import CleanMode, CleanPlan

from .conftest import FakeRobot

VACUUM = "vacuum.narwal"
# The synthetic map: origin (-3, -2.5) m, 50 mm cells, 120 x 100 cells.


async def _clean_zone(hass: HomeAssistant, **data) -> None:
    await hass.services.async_call(DOMAIN, "clean_zone", {ATTR_ENTITY_ID: VACUUM, **data}, blocking=True)


async def test_calibration_points(hass: HomeAssistant, init_integration) -> None:
    points = hass.states.get("image.narwal_map").attributes["calibration_points"]
    assert len(points) == 3
    (a, b, c) = points
    # Same image corner row for a and b, same column for a and c; 4 px per 50 mm cell.
    assert a["map"]["y"] == b["map"]["y"] and a["map"]["x"] == c["map"]["x"]
    assert (b["map"]["x"] - a["map"]["x"]) * 50 == (b["vacuum"]["x"] - a["vacuum"]["x"]) * 4
    assert (c["map"]["y"] - a["map"]["y"]) * 50 == (a["vacuum"]["y"] - c["vacuum"]["y"]) * 4, "image y points down"


async def test_clean_zones(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _clean_zone(hass, zones=[[-2000, -1500, -1000, -1000], [500, 500, 1500, 1200]], repeats=2)
    assert robot.calls[-1] == (
        "clean_zones",
        [(-2.0, -1.5, -1.0, -1.0), (0.5, 0.5, 1.5, 1.2)],
        CleanMode.SWEEP_MOP,
        2,
    )


@pytest.mark.parametrize(
    ("zone", "match"),
    [([50000, 50000, 60000, 60000], "outside the map"), ([0, 0, 10, 2000], "too small")],
)
async def test_bad_zones(hass: HomeAssistant, init_integration, robot: FakeRobot, zone, match) -> None:
    calls = len(robot.calls)
    with pytest.raises(ServiceValidationError, match=match):
        await _clean_zone(hass, zones=[zone])
    assert len(robot.calls) == calls


async def test_zone_schema(hass: HomeAssistant, init_integration) -> None:
    with pytest.raises(vol.Invalid):  # three numbers are not a rectangle
        await _clean_zone(hass, zones=[[0, 0, 1000]])
    with pytest.raises(vol.Invalid):
        await _clean_zone(hass, zones=[[0, 0, 1000, 1000]], repeats=4)


async def _next_map_read(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Plans are read together with the map."""
    freezer.tick(MAP_INTERVAL + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_plan_buttons_follow_the_app(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    assert "button.narwal_start_plan_kuche" not in hass.states.async_entity_ids("button")
    robot.plans = [CleanPlan(id=7, map_id=1, mode=CleanMode.SWEEP_MOP, custom=True, name="Küche")]
    await _next_map_read(hass, freezer)
    state = hass.states.get("button.narwal_start_plan_kuche")
    assert state is not None and state.attributes["friendly_name"] == "Narwal Start plan Küche"

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: state.entity_id}, blocking=True)
    assert robot.calls[-1] == ("start_plan", 7)

    robot.plans = []
    await _next_map_read(hass, freezer)
    assert hass.states.get("button.narwal_start_plan_kuche").state == STATE_UNAVAILABLE
