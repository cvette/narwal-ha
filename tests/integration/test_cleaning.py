"""Starting, stopping and locating; rooms as segments for vacuum.clean_area."""

from __future__ import annotations

from dataclasses import replace

import pytest

from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.vacuum import SERVICE_LOCATE, SERVICE_START, SERVICE_STOP
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar, entity_registry as er, issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.narwal_local.protocol import CleanMode, TaskType

from .conftest import FakeRobot, status_payload

VACUUM = "vacuum.narwal"
CLEAN_MODE = "select.narwal_cleaning_mode"
SEGMENTS = [
    {"id": "1", "name": "Living room", "group": None},
    {"id": "2", "name": "Kitchen", "group": None},
    {"id": "3", "name": "Hallway", "group": None},
    {"id": "4", "name": "Bedroom", "group": None},
]


async def _call(hass: HomeAssistant, domain: str, service: str, data: dict) -> None:
    await hass.services.async_call(domain, service, data, blocking=True)


async def test_start_cleans_every_room(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "vacuum", SERVICE_START, {ATTR_ENTITY_ID: VACUUM})
    assert ("start_clean", None, CleanMode.SWEEP_MOP) in robot.calls


async def test_start_resumes_when_paused(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    robot.push("/status/robot_base_status", status_payload({1: TaskType.SWEEP_AND_MOP, 2: 1, 6: 7}))
    await hass.async_block_till_done()
    assert hass.states.get(VACUUM).state == "paused"
    await _call(hass, "vacuum", SERVICE_START, {ATTR_ENTITY_ID: VACUUM})
    assert ("resume",) in robot.calls
    assert not any(call[0] == "start_clean" for call in robot.calls)


async def test_stop_and_locate(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    await _call(hass, "vacuum", SERVICE_STOP, {ATTR_ENTITY_ID: VACUUM})
    await _call(hass, "vacuum", SERVICE_LOCATE, {ATTR_ENTITY_ID: VACUUM})
    assert ("stop",) in robot.calls
    assert ("locate",) in robot.calls


async def test_clean_mode_select_sets_start_mode(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    state = hass.states.get(CLEAN_MODE)
    assert state.state == "vacuum_and_mop"
    assert state.attributes["options"] == ["vacuum_and_mop", "vacuum", "mop", "vacuum_then_mop"]
    await _call(hass, "select", SERVICE_SELECT_OPTION, {ATTR_ENTITY_ID: CLEAN_MODE, ATTR_OPTION: "vacuum"})
    await _call(hass, "vacuum", SERVICE_START, {ATTR_ENTITY_ID: VACUUM})
    assert ("start_clean", None, CleanMode.SWEEP) in robot.calls


async def test_clean_mode_is_restored(
    hass: HomeAssistant, robot: FakeRobot, config_entry: MockConfigEntry
) -> None:
    mock_restore_cache(hass, [State(CLEAN_MODE, "mop")])
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(CLEAN_MODE).state == "mop"
    assert config_entry.runtime_data.clean_mode is CleanMode.MOP


async def test_rooms_are_segments(hass: HomeAssistant, init_integration, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "vacuum/get_segments", "entity_id": VACUUM})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["segments"] == SEGMENTS


async def test_clean_area_cleans_mapped_rooms_in_order(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    areas = ar.async_get(hass)
    kitchen = areas.async_create("Küche")
    hall = areas.async_create("Diele")
    registry = er.async_get(hass)
    registry.async_update_entity_options(
        VACUUM,
        "vacuum",
        {
            "area_mapping": {kitchen.id: ["2"], hall.id: ["3"]},
            "last_seen_segments": SEGMENTS,
        },
    )
    await hass.async_block_till_done()

    await _call(hass, "vacuum", "clean_area", {ATTR_ENTITY_ID: VACUUM, "cleaning_area_id": [hall.id, kitchen.id]})
    assert ("start_clean", [3, 2], CleanMode.SWEEP_MOP) in robot.calls

    with pytest.raises(ServiceValidationError):
        await _call(hass, "vacuum", "clean_area", {ATTR_ENTITY_ID: VACUUM, "cleaning_area_id": ["unmapped"]})


async def test_changed_rooms_raise_a_repair_issue(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    registry = er.async_get(hass)
    registry.async_update_entity_options(
        VACUUM, "vacuum", {"area_mapping": {}, "last_seen_segments": SEGMENTS}
    )
    await hass.async_block_till_done()
    entry_id = registry.async_get(VACUUM).id
    issues = ir.async_get(hass)
    assert issues.async_get_issue("vacuum", f"segments_changed_{entry_id}") is None

    # The user renames a room in the app; the next map fetch brings it in.
    coordinator = init_integration.runtime_data
    new_map = replace(
        robot.map,
        edit_version=robot.map.edit_version + 1,
        rooms=[replace(r, name="Office") if r.id == 4 else r for r in robot.map.rooms],
    )
    coordinator.async_set_updated_data(replace(coordinator.data, map=new_map))
    await hass.async_block_till_done()
    assert issues.async_get_issue("vacuum", f"segments_changed_{entry_id}") is not None
