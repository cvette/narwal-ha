"""Select entities."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .protocol import MopHumidity

PARALLEL_UPDATES = 1

MOP_OPTIONS: dict[MopHumidity, str] = {
    MopHumidity.DRY: "dry",
    MopHumidity.NORMAL: "normal",
    MopHumidity.WET: "wet",
}
MOP_LEVELS = {name: level for level, name in MOP_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NarwalMopHumiditySelect(entry.runtime_data)])


class NarwalMopHumiditySelect(NarwalEntity, SelectEntity):
    _attr_translation_key = "mop_humidity"
    _attr_options = list(MOP_OPTIONS.values())

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "mop_humidity")

    @property
    def current_option(self) -> str | None:
        return MOP_OPTIONS.get(self.coordinator.data.status.mop_humidity)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(
            self.coordinator.robot.set_mop_humidity(MOP_LEVELS[option])
        )
        await self.coordinator.async_request_refresh()
