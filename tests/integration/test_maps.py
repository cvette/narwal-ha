"""The map select (several maps / floors)."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.narwal_local.const import MAP_INTERVAL
from custom_components.narwal_local.protocol import MapSummary

from .conftest import FakeRobot

SELECT = "select.narwal_map"


async def test_single_map(hass: HomeAssistant, init_integration) -> None:
    state = hass.states.get(SELECT)
    assert state.state == "Map 1", "an unnamed map is offered by its number"
    assert state.attributes["options"] == ["Map 1"]


async def test_switch_to_another_floor(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    robot.maps.append(MapSummary(2, "Upstairs"))
    freezer.tick(MAP_INTERVAL + timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).attributes["options"] == ["Map 1", "Upstairs"]

    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT, "option": "Upstairs"}, blocking=True
    )
    assert ("switch_map", 2) in robot.calls


async def test_no_map_select_without_multi_map(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    robot.features.flags["supportMultiMap"] = False
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SELECT) is None


async def test_selecting_the_current_map_sends_nothing(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    calls = len(robot.calls)
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: SELECT, "option": "Map 1"}, blocking=True
    )
    assert len(robot.calls) == calls, "the robot rejects switching to its current map"
