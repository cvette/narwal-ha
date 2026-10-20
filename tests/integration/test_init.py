"""Setup, unload, connection handling and diagnostics."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.narwal_local.const import DOMAIN
from custom_components.narwal_local.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_ID, FakeRobot


async def test_setup_and_unload(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    assert init_integration.state is ConfigEntryState.LOADED
    assert robot.connected
    assert ("activate_reporting", 60) in robot.calls

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), init_integration.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, DEVICE_ID)}
    assert device.manufacturer == "Narwal"
    assert device.sw_version == "v01.09.05.04"

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert not robot.connected
    assert not robot.push_callbacks and not robot.disconnect_callbacks


async def test_setup_retries_when_unreachable(
    hass: HomeAssistant, robot: FakeRobot, config_entry
) -> None:
    robot.fail_connect = True
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_disconnect_marks_unavailable_and_reconnects(
    hass: HomeAssistant, init_integration, robot: FakeRobot
) -> None:
    assert hass.states.get("vacuum.narwal").state == "docked"

    robot.fail_connect = True
    robot.drop()
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.narwal").state == STATE_UNAVAILABLE

    robot.fail_connect = False
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert robot.connected
    assert hass.states.get("vacuum.narwal").state == "docked"


async def test_keepalive_rearms_reporting(hass: HomeAssistant, init_integration, robot: FakeRobot) -> None:
    before = robot.calls.count(("activate_reporting", 60))
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=46))
    await hass.async_block_till_done()
    assert robot.calls.count(("activate_reporting", 60)) > before


async def test_diagnostics_redacts_ids(hass: HomeAssistant, init_integration) -> None:
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    assert diag["device"]["token"] == "**REDACTED**"
    assert diag["device"]["device_id"] == "**REDACTED**"
    assert diag["status"]["binded_uuid"] == "**REDACTED**"
    assert diag["status"]["activity"] == "docked"
    assert [r["name"] for r in diag["map"]["rooms"]] == ["Living room", "Kitchen", "Hallway", "Bedroom"]
