"""The map card's backend: websocket map data, clean_rooms, the served script."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.narwal_local.const import DOMAIN
from custom_components.narwal_local.map_card import CARD_URL
from custom_components.narwal_local.protocol import CleanMode

from .conftest import FakeRobot, display_map_payload, status_payload
from .test_position import CLEANING

VACUUM = "vacuum.narwal"


async def test_map_over_websocket(hass: HomeAssistant, init_integration, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/map", "entity_id": VACUUM})
    msg = await client.receive_json()
    assert msg["success"], msg
    result = msg["result"]
    assert result["image"].startswith("data:image/png;base64,")
    assert result["position_entity"] == "sensor.narwal_position"
    assert result["battery_entity"] == "sensor.narwal_battery"
    assert [r["name"] for r in result["rooms"]] == ["Living room", "Kitchen", "Hallway", "Bedroom"]
    assert result["path"] == []

    # Same version: only the live part comes back.
    await client.send_json_auto_id({"type": f"{DOMAIN}/map", "entity_id": VACUUM, "version": result["version"]})
    again = (await client.receive_json())["result"]
    assert "image" not in again and again["version"] == result["version"]


async def test_map_includes_the_current_path(
    hass: HomeAssistant, init_integration, robot: FakeRobot, hass_ws_client
) -> None:
    robot.push("/status/robot_base_status", status_payload(CLEANING))
    robot.push("/map/display_map", display_map_payload(45, 20))
    robot.push("/map/display_map", display_map_payload(60, 20))
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/map", "entity_id": VACUUM})
    path = (await client.receive_json())["result"]["path"]
    assert path == [[-0.75, -1.5], [0.0, -1.5]]


async def test_map_for_other_entities(hass: HomeAssistant, init_integration, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/map", "entity_id": "light.kitchen"})
    msg = await client.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "not_found"


async def test_clean_rooms(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await hass.services.async_call(
        DOMAIN, "clean_rooms", {ATTR_ENTITY_ID: VACUUM, "rooms": [3, 1], "repeats": 2}, blocking=True
    )
    assert robot.calls[-1] == ("start_clean", [3, 1], CleanMode.SWEEP_MOP)
    with pytest.raises(ServiceValidationError, match="no room with id 9"):
        await hass.services.async_call(DOMAIN, "clean_rooms", {ATTR_ENTITY_ID: VACUUM, "rooms": [9]}, blocking=True)


async def test_card_script_is_served(hass: HomeAssistant, init_integration, hass_client) -> None:
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert "customElements.define(\"narwal-map-card\"" in await response.text()


async def test_card_is_added_to_the_frontend(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    hass.config.components.add("frontend")
    with patch("custom_components.narwal_local.map_card.add_extra_js_url") as add:
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    [(_, url)] = [c.args for c in add.call_args_list]
    assert url.startswith(f"{CARD_URL}?v=")
