"""No-go zones: actions, the map image's list, the card's data."""

from __future__ import annotations

import pytest

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.narwal_local.const import DOMAIN
from custom_components.narwal_local.protocol import ForbiddenType, NoGoZone, ServiceResult

from .conftest import FakeRobot

VACUUM = "vacuum.narwal"
IMAGE = "image.narwal_map"
# The synthetic map has one no-entry zone (id 1) at (1.25..1.75, -0.75..-0.25) m.


async def _call(hass: HomeAssistant, service: str, **data) -> None:
    await hass.services.async_call(DOMAIN, service, {ATTR_ENTITY_ID: VACUUM, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_no_go_zones_on_the_map(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get(IMAGE).attributes["no_go_zones"] == [
        {"id": 1, "type": "no_entry", "room_wide": False, "bounds": [1250, -750, 1750, -250]}
    ]


async def test_add_no_go_zones(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "add_no_go_zones", zones=[[-2000, -1500, -1500, -1000]], type="no_mop")
    assert robot.calls[-1] == ("edit_no_go_zones", [NoGoZone(-2.0, -1.5, -1.5, -1.0, ForbiddenType.MOP)], [])
    zones = hass.states.get(IMAGE).attributes["no_go_zones"]
    assert [(z["id"], z["type"]) for z in zones] == [(1, "no_entry"), (2, "no_mop")], "map taken from the robot"
    assert zones[1]["bounds"] == [-2000, -1500, -1500, -1000]


async def test_delete_no_go_zones(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    with pytest.raises(ServiceValidationError, match="id 5"):
        await _call(hass, "delete_no_go_zones", ids=[5])
    await _call(hass, "delete_no_go_zones")  # all
    assert robot.calls[-1] == ("edit_no_go_zones", [], [1])
    assert hass.states.get(IMAGE).attributes["no_go_zones"] == []
    calls = len(robot.calls)
    await _call(hass, "delete_no_go_zones")
    assert len(robot.calls) == calls, "nothing left to delete"


async def test_rejected_edit(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    robot.fail_command = ServiceResult.PERFORM_GENERAL_FAILED
    with pytest.raises(HomeAssistantError):
        await _call(hass, "add_no_go_zones", zones=[[0, 0, 500, 500]])
    assert len(hass.states.get(IMAGE).attributes["no_go_zones"]) == 1


async def test_card_gets_no_go_zones(hass: HomeAssistant, init_integration, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/map", "entity_id": VACUUM})
    [zone] = (await client.receive_json())["result"]["no_go_zones"]
    assert zone["id"] == 1 and zone["type"] == 3 and len(zone["points"]) == 4
