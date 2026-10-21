"""Map image entity."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import FakeRobot

IMAGE = "image.narwal_map"


async def test_map_image_served_as_png(hass: HomeAssistant, init_integration, hass_client) -> None:
    state = hass.states.get(IMAGE)
    assert state is not None and state.state not in ("unavailable", "unknown")
    assert state.attributes["rooms"] == [
        {"id": 1, "name": "Living room"},
        {"id": 2, "name": "Kitchen"},
        {"id": 3, "name": "Hallway"},
        {"id": 4, "name": "Bedroom"},
    ]

    assert state.attributes["dock_room"] == "Living room"
    assert state.attributes["furniture"] == [
        {"id": 1, "type": "sofa_multi", "name": "Sofa", "room": "Living room"},
        {"id": 2, "type": "double_bed", "name": "Double bed", "room": "Bedroom"},
    ]
    assert state.attributes["obstacles"] == [
        {"id": 1, "type": "cable", "name": "Cable", "room": "Living room"},
        {"id": 2, "type": "socks", "name": "Socks", "room": "Hallway"},
        {"id": 3, "type": "poop", "name": "Pet waste", "room": "Kitchen"},
    ]
    assert state.attributes["dirt"] == [
        {"id": 1, "type": "liquid_many", "name": "Liquid stain", "status": "cleaned", "room": "Kitchen"}
    ]

    client = await hass_client()
    resp = await client.get(f"/api/image_proxy/{IMAGE}")
    assert resp.status == HTTPStatus.OK
    assert resp.content_type == "image/png"
    body = await resp.read()
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_map_change_rerenders(
    hass: HomeAssistant, init_integration, robot: FakeRobot, hass_client, freezer
) -> None:
    before = hass.states.get(IMAGE).state
    client = await hass_client()
    first = await (await client.get(f"/api/image_proxy/{IMAGE}")).read()

    # A room rename in the app bumps the edit version; the coordinator picks the
    # new map up on its next map refresh (every 15 minutes).
    robot.map = replace(
        robot.map,
        edit_version=robot.map.edit_version + 1,
        rooms=[replace(r, name="Office") if r.id == 4 else r for r in robot.map.rooms],
    )
    await _advance(hass, freezer, timedelta(minutes=16))

    state = hass.states.get(IMAGE)
    assert state.state != before, "image_last_updated must move on"
    assert {"id": 4, "name": "Office"} in state.attributes["rooms"]
    second = await (await client.get(f"/api/image_proxy/{IMAGE}")).read()
    assert second != first


async def test_detected_obstacles_sensor(hass: HomeAssistant, init_integration) -> None:
    state = hass.states.get("sensor.narwal_detected_obstacles")
    assert state.state == "3"
    assert [o["type"] for o in state.attributes["obstacles"]] == ["cable", "socks", "poop"]


async def test_last_detected_sensor(hass: HomeAssistant, init_integration) -> None:
    assert hass.states.get("sensor.narwal_last_detected").state == "1× Cable, 1× Pet waste, 1× Socks"


async def test_names_follow_ha_language(
    hass: HomeAssistant, robot: FakeRobot, config_entry, hass_client
) -> None:
    hass.config.language = "de"
    robot.map = replace(robot.map, obstacles=robot.map.obstacles + robot.map.obstacles[:1])
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Entity ids come from the German names now.
    state = hass.states.get("sensor.narwal_zuletzt_erkannt")
    assert state.state == "2× Kabel, 1× Haustierkot, 1× Socken"
    obstacles = hass.states.get("sensor.narwal_erkannte_hindernisse").attributes["obstacles"]
    assert [o["name"] for o in obstacles] == ["Kabel", "Socken", "Haustierkot", "Kabel"]
    assert [o["type"] for o in obstacles] == ["cable", "socks", "poop", "cable"], "types stay stable keys"
    furniture = hass.states.get("image.narwal_karte").attributes["furniture"]
    assert [f["name"] for f in furniture] == ["Sofa", "Doppelbett"]
    client = await hass_client()
    resp = await client.get("/api/image_proxy/image.narwal_karte")
    assert resp.status == HTTPStatus.OK


async def test_new_detection_rerenders(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer
) -> None:
    """A clean can add detections without an edit-version bump."""
    before = hass.states.get(IMAGE).state
    robot.map = replace(robot.map, obstacles=robot.map.obstacles[:1])
    await _advance(hass, freezer, timedelta(minutes=16))
    assert hass.states.get(IMAGE).state != before
    assert hass.states.get("sensor.narwal_detected_obstacles").state == "1"
    assert hass.states.get("sensor.narwal_last_detected").state == "1× Cable"

    robot.map = replace(robot.map, obstacles=[])
    await _advance(hass, freezer, timedelta(minutes=16))
    assert hass.states.get("sensor.narwal_last_detected").state == "None"


async def test_unchanged_map_keeps_timestamp(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer
) -> None:
    before = hass.states.get(IMAGE).state
    fetched = robot.map_fetches
    await _advance(hass, freezer, timedelta(minutes=16))
    assert robot.map_fetches > fetched, "the map must have been fetched again"
    assert hass.states.get(IMAGE).state == before
