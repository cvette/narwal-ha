"""Local control of Narwal robot vacuums."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, DOMAIN, REPORT_SECONDS
from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalStatic
from .protocol import NarwalError, NarwalRobot

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.IMAGE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.VACUUM,
]


async def async_setup_entry(hass: HomeAssistant, entry: NarwalConfigEntry) -> bool:
    """Connect, read static device data, then start the coordinator."""
    robot = NarwalRobot(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        session=async_get_clientsession(hass),
    )
    try:
        await robot.connect()
        device = await robot.get_device_info()
        features = await robot.get_features()
        firmware = (
            await robot.get_firmware_version()
            if features.supports("supportGetFirmwareVersion")
            else None
        )
        await robot.activate_reporting(REPORT_SECONDS)
    except NarwalError as err:
        await robot.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST], "error": str(err)},
        ) from err

    coordinator = NarwalCoordinator(hass, entry, robot, NarwalStatic(device, features, firmware))
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await robot.close()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NarwalConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded
