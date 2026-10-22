"""Station action buttons."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.narwal_local.protocol import ServiceResult

from .conftest import FakeRobot


async def _press(hass: HomeAssistant, entity: str) -> None:
    await hass.services.async_call("button", SERVICE_PRESS, {ATTR_ENTITY_ID: entity}, blocking=True)


@pytest.mark.parametrize(
    ("entity", "call"),
    [
        ("button.narwal_empty_dust_bin", "empty_dust_bin"),
        ("button.narwal_wash_mop", "wash_mop"),
        ("button.narwal_dry_mop", "dry_mop"),
    ],
)
async def test_station_buttons(
    hass: HomeAssistant, init_integration, robot: FakeRobot, entity: str, call: str
) -> None:
    await _press(hass, entity)
    assert robot.calls[-1] == (call,)


async def test_rejected_station_action_raises(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    robot.fail_command = ServiceResult.ROBOT_NOT_CONTACT_WITH_STATION
    with pytest.raises(HomeAssistantError):
        await _press(hass, "button.narwal_wash_mop")


async def test_no_buttons_without_station(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.status = replace(robot.status, has_station=False)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("button.narwal_wash_mop") is None
