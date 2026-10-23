"""Local control of Narwal robot vacuums."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_PORT, DOMAIN, REPORT_SECONDS
from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalStatic
from .map_card import async_forget_map, async_setup_card
from .map_objects import async_load_names
from .protocol import NarwalError, NarwalRobot
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.VACUUM,
]


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions and the map card once, for all robots."""
    async_setup_services(hass)
    await async_setup_card(hass)
    return True


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
        languages: tuple = ()
        if features.supports("supportOperateLanguage"):
            try:
                languages = tuple(await robot.get_supported_languages())
            except NarwalError:
                languages = ()
        await robot.activate_reporting(REPORT_SECONDS)
    except NarwalError as err:
        await robot.close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST], "error": str(err)},
        ) from err

    coordinator = NarwalCoordinator(
        hass, entry, robot, NarwalStatic(device, features, firmware, languages), await async_load_names(hass)
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await robot.close()
        raise
    entry.runtime_data = coordinator
    _remove_retired_entities(hass, coordinator.device_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


# Entities earlier versions created that no longer exist (unique-id suffixes).
RETIRED_SENSORS = ("remaining_time",)  # the robot always reported 0


def _remove_retired_entities(hass: HomeAssistant, device_id: str) -> None:
    registry = er.async_get(hass)
    for key in RETIRED_SENSORS:
        if entity_id := registry.async_get_entity_id(Platform.SENSOR, DOMAIN, f"{device_id}_{key}"):
            registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: NarwalConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        async_forget_map(hass, entry.entry_id)
    return unloaded
