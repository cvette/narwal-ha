"""Actions: reset consumable reminders, clean zones."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, service

from .const import DOMAIN
from .coordinator import NarwalConfigEntry
from .protocol.enums import MAINTAIN_ITEM_NAMES, REPLACE_ITEM_NAMES

SERVICE_RESET_CONSUMABLES = "reset_consumables"
SERVICE_CLEAN_ZONE = "clean_zone"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ITEMS = "items"

CONSUMABLE_ITEMS: list[str] = sorted(
    {*MAINTAIN_ITEM_NAMES.values(), *REPLACE_ITEM_NAMES.values()} - {"unspecified"}
)

MAX_ZONES = 10  # the app's limit for drawn areas

ZONE = vol.All(list, vol.Length(min=4, max=4), [vol.Coerce(float)])
CLEAN_ZONE_SCHEMA = {
    vol.Required("zones"): vol.All(cv.ensure_list, [ZONE], vol.Length(min=1, max=MAX_ZONES)),
    vol.Optional("repeats", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
}

RESET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_ITEMS): vol.All(cv.ensure_list, [vol.In(CONSUMABLE_ITEMS)]),
    }
)


def _entry(hass: HomeAssistant, entry_id: str) -> NarwalConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    return entry


async def _async_reset_consumables(call: ServiceCall) -> None:
    """Clear the robot's reminders for parts that are due: the given ones, or
    all due parts. Lifetimes in the Narwal app are kept in Narwal's cloud and
    are not touched."""
    coordinator = _entry(call.hass, call.data[ATTR_CONFIG_ENTRY_ID]).runtime_data
    due = coordinator.data.consumables
    due_maintain = due.maintain_items if due else []
    due_replace = due.replace_items if due else []
    items: list[str] = call.data.get(ATTR_ITEMS) or [*due_maintain, *due_replace]
    if not items:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="nothing_due")
    for item in items:
        if item not in due_maintain and item not in due_replace:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_due",
                translation_placeholders={"item": coordinator.names.consumable(item)},
            )
    await coordinator.async_command(
        coordinator.robot.reset_consumables(
            [i for i in items if i in due_maintain], [i for i in items if i in due_replace]
        )
    )
    await coordinator.async_refresh_consumables()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_CONSUMABLES, _async_reset_consumables, schema=RESET_SCHEMA
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        entity_domain=VACUUM_DOMAIN,
        schema=CLEAN_ZONE_SCHEMA,
        func="async_clean_zone",
    )
