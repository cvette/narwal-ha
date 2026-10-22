"""Consumable reminders: readable names and the reset action."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.narwal_local.const import DOMAIN

from .conftest import FakeRobot

# The fixture robot reports: clean the side distance sensor, replace the station bag.
MAINTAIN = "sensor.narwal_maintenance_due"
REPLACE = "sensor.narwal_replacement_due"


async def _reset(hass: HomeAssistant, entry_id: str, **data) -> None:
    await hass.services.async_call(
        DOMAIN, "reset_consumables", {"config_entry_id": entry_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_due_parts_have_names(hass: HomeAssistant, init_integration) -> None:
    state = hass.states.get(MAINTAIN)
    assert state.state == "1"
    assert state.attributes["items"] == ["side_distance_sensor"]
    assert state.attributes["names"] == ["Side distance sensor"]
    assert hass.states.get(REPLACE).attributes["names"] == ["Station dust bag"]


async def test_reset_one_part(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _reset(hass, init_integration.entry_id, items=["station_bag"])
    assert robot.calls[-1] == ("reset_consumables", [], ["station_bag"])
    assert hass.states.get(REPLACE).state == "0"
    assert hass.states.get(MAINTAIN).state == "1"


async def test_reset_all_due_parts(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _reset(hass, init_integration.entry_id)
    assert robot.calls[-1] == ("reset_consumables", ["side_distance_sensor"], ["station_bag"])
    assert hass.states.get(MAINTAIN).state == "0"

    with pytest.raises(ServiceValidationError, match="No part is due"):
        await _reset(hass, init_integration.entry_id)


async def test_reset_part_that_is_not_due(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    calls = len(robot.calls)
    with pytest.raises(ServiceValidationError, match="Side brush is not due"):
        await _reset(hass, init_integration.entry_id, items=["side_brush"])
    assert len(robot.calls) == calls, "nothing is sent"


async def test_reset_unknown_entry(hass: HomeAssistant, init_integration) -> None:
    with pytest.raises(ServiceValidationError):
        await _reset(hass, "not-an-entry")
